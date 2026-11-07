"""Download and convert NASA C-MAPSS FD001.

The raw archive is not stored in this repository. ``rulsafe data fetch cmapss``
downloads the NASA Prognostics outer zip, checks its SHA-256, then checks the
inner ``CMAPSSData.zip`` and writes Parquet tables plus split id files under
``data/cmapss/``. That directory is git-ignored. ``--from-file`` accepts either
zip when the network is not used.

FD001 training engines run until failure and are split for fit and for the
secondary per-row view. FD001 test engines stop before failure. They stay
out of training. ``RUL_FD001.txt`` is written beside the tables as official
last-observation truth and is not a training label.
"""

import hashlib
import secrets
import tempfile
import urllib.error
import urllib.request
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path

from rulsafe.exceptions import ConfigurationError
from rulsafe.pipeline.split import SplitName, partition_in_given_order

# NASA Prognostics Data Repository distribution. The catalog page is
# https://data.nasa.gov/dataset/cmapss-jet-engine-simulated-data
# and does not state a licence. This outer zip contains CMAPSSData.zip.
CMAPSS_ARCHIVE_URL = (
    "https://phm-datasets.s3.amazonaws.com/NASA/"
    "6.+Turbofan+Engine+Degradation+Simulation+Data+Set.zip"
)
# SHA-256 of the outer zip at CMAPSS_ARCHIVE_URL. 12,429,152 bytes.
CMAPSS_OUTER_SHA256 = "c9c5dec12a945a82e8bb4446589d7fb3cc057b5e5d81fa1a12e25ee9912ad3b2"
# SHA-256 of the inner CMAPSSData.zip. 12,425,978 bytes.
CMAPSS_INNER_SHA256 = "74bef434a34db25c7bf72e668ea4cd52afe5f2cf8e44367c55a82bfd91a5a34f"
CMAPSS_ARCHIVE_SHA256 = CMAPSS_INNER_SHA256
_INNER_ARCHIVE_NAME = "CMAPSSData.zip"
_FD001_MEMBERS = ("train_FD001.txt", "test_FD001.txt", "RUL_FD001.txt")
_FD001_COLUMNS: tuple[str, ...] = (
    "unit_id",
    "cycle",
    "setting_1",
    "setting_2",
    "setting_3",
    *(f"sensor_{index}" for index in range(1, 22)),
)
_COMPLETED_PREFIX = "train"
_CENSORED_PREFIX = "test"
_DOWNLOAD_ATTEMPTS = 3
_MAX_MEMBER_BYTES = 80_000_000


def fetch_cmapss_fd001(
    destination: Path,
    *,
    archive: Path | None = None,
    url: str = CMAPSS_ARCHIVE_URL,
    outer_sha256: str = CMAPSS_OUTER_SHA256,
    inner_sha256: str = CMAPSS_INNER_SHA256,
) -> Path:
    """Download or open a local zip, verify the pinned hashes, and convert FD001.

    A download must be the outer Prognostics zip. ``archive`` may be that outer
    zip or the inner ``CMAPSSData.zip``. Either way the inner hash is checked
    before a table is written. The download is not kept.

    Args:
        destination: Directory for the Parquet tables and id files.
        archive: Local outer or inner zip. When omitted, ``url`` is downloaded.
        url: HTTPS URL of the outer NASA zip. Used only when ``archive`` is omitted.
        outer_sha256: Pinned SHA-256 of the outer zip.
        inner_sha256: Pinned SHA-256 of ``CMAPSSData.zip``.

    Returns:
        ``destination`` after the converted files have been written.

    Raises:
        ConfigurationError: The download fails, a hash does not match, or the
            archive is not FD001.
    """
    with tempfile.TemporaryDirectory() as temporary_name:
        temporary = Path(temporary_name)
        if archive is None:
            downloaded = temporary / "outer.zip"
            _download_archive(url, downloaded)
            verify_sha256(downloaded, outer_sha256)
            source = downloaded
        else:
            source = archive
        inner = _resolve_inner_archive(
            source,
            temporary,
            outer_sha256=outer_sha256,
            inner_sha256=inner_sha256,
        )
        convert_fd001_archive(inner, destination)
    return destination


def _resolve_inner_archive(
    source: Path,
    work: Path,
    *,
    outer_sha256: str,
    inner_sha256: str,
) -> Path:
    """Return the inner C-MAPSS zip after checking the pinned digest.

    Args:
        source: Outer zip or inner ``CMAPSSData.zip``.
        work: Directory for an extracted inner zip.
        outer_sha256: Pinned outer digest.
        inner_sha256: Pinned inner digest.

    Returns:
        Path of the verified inner zip.

    Raises:
        ConfigurationError: The file matches neither pin, or the inner member
            does not match ``inner_sha256``.
    """
    digest = _sha256(source)
    if secrets.compare_digest(digest, _normalized_sha256(inner_sha256)):
        return source
    if secrets.compare_digest(digest, _normalized_sha256(outer_sha256)):
        extracted = work / _INNER_ARCHIVE_NAME
        _extract_named_member(source, _INNER_ARCHIVE_NAME, extracted)
        verify_sha256(extracted, inner_sha256)
        return extracted
    raise ConfigurationError(
        "SHA-256 mismatch. Expected the NASA Prognostics outer zip "
        f"{_normalized_sha256(outer_sha256)} or the inner CMAPSSData.zip "
        f"{_normalized_sha256(inner_sha256)}. Computed {digest}."
    )


def verify_sha256(path: Path, expected_sha256: str) -> str:
    """Check the SHA-256 of a file.

    Args:
        path: File to hash.
        expected_sha256: Expected lowercase or uppercase hex digest.

    Returns:
        The computed lowercase digest.

    Raises:
        ConfigurationError: The file is missing or the digest differs.
    """
    digest = _sha256(path)
    expected = _normalized_sha256(expected_sha256)
    if not secrets.compare_digest(digest, expected):
        raise ConfigurationError(
            f"SHA-256 mismatch for {path.name}. Expected {expected}, computed {digest}."
        )
    return digest


def _sha256(path: Path) -> str:
    """Return the lowercase SHA-256 of a file.

    Args:
        path: File to hash.

    Returns:
        The hex digest.

    Raises:
        ConfigurationError: The file cannot be read.
    """
    if not path.is_file():
        raise ConfigurationError(f"Could not read archive {path}.")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalized_sha256(expected_sha256: str) -> str:
    """Return a lowercase SHA-256 hex digest.

    Args:
        expected_sha256: Hex digest.

    Returns:
        The stripped lowercase digest.

    Raises:
        ConfigurationError: The value is not 64 hex characters.
    """
    expected = expected_sha256.strip().casefold()
    if len(expected) != 64 or any(character not in "0123456789abcdef" for character in expected):
        raise ConfigurationError("A SHA-256 pin must be 64 hex characters.")
    return expected


def _extract_named_member(archive: Path, member_name: str, destination: Path) -> None:
    """Copy one zip member, matched by basename, into ``destination``.

    Args:
        archive: Zip file.
        member_name: Basename to find. Directory prefixes are ignored.
        destination: Output path. The member is not extracted with its
            archive path.

    Raises:
        ConfigurationError: The member is missing, repeated, or too large.
    """
    try:
        with zipfile.ZipFile(archive) as bundle:
            matches = [
                info
                for info in bundle.infolist()
                if not info.is_dir() and Path(info.filename).name == member_name
            ]
            if len(matches) != 1:
                raise ConfigurationError(
                    f"Expected one {member_name} in {archive.name}, found {len(matches)}."
                )
            info = matches[0]
            if info.file_size > _MAX_MEMBER_BYTES:
                raise ConfigurationError(f"Archive member {info.filename} is too large.")
            destination.write_bytes(bundle.read(info))
    except zipfile.BadZipFile as error:
        raise ConfigurationError(f"{archive.name} is not a zip archive.") from error
    except OSError as error:
        raise ConfigurationError(f"Could not read archive {archive}.") from error


def convert_fd001_archive(archive: Path, destination: Path) -> dict[str, int]:
    """Convert FD001 members of a C-MAPSS zip into the demo tables.

    Args:
        archive: Zip that contains ``train_FD001.txt``, ``test_FD001.txt``,
            and ``RUL_FD001.txt``.
        destination: Directory for the converted files.

    Returns:
        Counts of completed engines, censored engines, and each split.

    Raises:
        ConfigurationError: A required member is missing or the tables are
            not a usable FD001 extract.
    """
    members = _read_fd001_members(archive)
    train_rows = _parse_trajectory(members["train_FD001.txt"], _COMPLETED_PREFIX)
    test_rows = _parse_trajectory(members["test_FD001.txt"], _CENSORED_PREFIX)
    rul_values = _parse_rul(members["RUL_FD001.txt"])
    if len(rul_values) != len({row["unit_id"] for row in test_rows}):
        raise ConfigurationError(
            "RUL_FD001.txt does not have one value per FD001 test engine. "
            "Those values are official test truth, not training labels."
        )
    completed_ids = _ordered_unit_ids(train_rows)
    censored_ids = _ordered_unit_ids(test_rows)
    if set(completed_ids) & set(censored_ids):
        raise ConfigurationError("A training engine id collides with a test engine id.")
    splits = partition_in_given_order(completed_ids)
    assets = [{"unit_id": asset_id} for asset_id in (*completed_ids, *censored_ids)]
    events = _events(train_rows, event_type="failure") + _events(test_rows, event_type="censored")
    destination.mkdir(parents=True, exist_ok=True)
    _write_parquet(destination / "fd001_assets.parquet", assets)
    _write_parquet(destination / "fd001_signals.parquet", train_rows + test_rows)
    _write_parquet(destination / "fd001_events.parquet", events)
    _write_ids(destination / "fd001_train_ids.txt", splits[SplitName.TRAIN])
    _write_ids(destination / "fd001_validation_ids.txt", splits[SplitName.VALIDATION])
    _write_ids(destination / "fd001_test_ids.txt", splits[SplitName.TEST])
    _write_official_rul(destination / "fd001_official_rul.txt", censored_ids, rul_values)
    return {
        "completed_engines": len(completed_ids),
        "censored_engines": len(censored_ids),
        "train_engines": len(splits[SplitName.TRAIN]),
        "validation_engines": len(splits[SplitName.VALIDATION]),
        "test_engines": len(splits[SplitName.TEST]),
    }


def _download_archive(url: str, destination: Path) -> None:
    """Download an HTTPS archive, retrying a few times.

    Args:
        url: NASA archive URL.
        destination: Where the zip is written.

    Raises:
        ConfigurationError: The URL is not HTTPS, or every attempt fails.
    """
    if not url.startswith("https://"):
        raise ConfigurationError(f"The C-MAPSS archive URL must be https. Got {url!r}.")
    last_error: Exception | None = None
    for _attempt in range(_DOWNLOAD_ATTEMPTS):
        try:
            # The URL is the pinned NASA HTTPS distribution, not a caller redirect.
            request = urllib.request.Request(  # noqa: S310
                url, headers={"User-Agent": "rulsafe/0.1"}
            )
            with urllib.request.urlopen(request, timeout=180) as response:  # noqa: S310  # nosec B310
                destination.write_bytes(response.read())
            return
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            last_error = error
    raise ConfigurationError(
        f"Could not download the C-MAPSS archive from {url}: {last_error}"
    ) from last_error


def _read_fd001_members(archive: Path) -> dict[str, str]:
    """Read the three FD001 text members from a zip.

    Args:
        archive: C-MAPSS zip.

    Returns:
        Member basename to decoded text.

    Raises:
        ConfigurationError: The zip is unreadable or a member is missing.
    """
    if not archive.is_file():
        raise ConfigurationError(f"Could not read archive {archive}.")
    try:
        with zipfile.ZipFile(archive) as bundle:
            chosen: dict[str, str] = {}
            for info in bundle.infolist():
                if info.is_dir():
                    continue
                if info.file_size > _MAX_MEMBER_BYTES:
                    raise ConfigurationError(f"Archive member {info.filename} is too large.")
                name = Path(info.filename).name
                if name not in _FD001_MEMBERS:
                    continue
                if name in chosen:
                    raise ConfigurationError(f"Archive contains more than one {name}.")
                chosen[name] = bundle.read(info).decode("utf-8")
    except zipfile.BadZipFile as error:
        raise ConfigurationError(f"{archive.name} is not a zip archive.") from error
    except OSError as error:
        raise ConfigurationError(f"Could not read archive {archive}.") from error
    missing = [name for name in _FD001_MEMBERS if name not in chosen]
    if missing:
        raise ConfigurationError(
            "The archive is missing FD001 members: " + ", ".join(missing) + "."
        )
    return chosen


def _parse_trajectory(text: str, prefix: str) -> list[dict[str, str]]:
    """Parse a whitespace-separated FD001 trajectory file.

    Args:
        text: File body.
        prefix: ``train`` or ``test``, used in the asset id.

    Returns:
        Signal rows with ``unit_id`` namespaced by ``prefix``.

    Raises:
        ConfigurationError: A row does not have the FD001 column count.
    """
    rows: list[dict[str, str]] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        cells = raw_line.split()
        if not cells:
            continue
        if len(cells) != len(_FD001_COLUMNS):
            raise ConfigurationError(
                f"FD001 row {line_number} has {len(cells)} columns, expected {len(_FD001_COLUMNS)}."
            )
        unit_token = cells[0]
        if not unit_token.isdigit():
            raise ConfigurationError(f"FD001 unit id {unit_token!r} is not an integer.")
        record = dict(zip(_FD001_COLUMNS, cells, strict=True))
        record["unit_id"] = f"{prefix}-{int(unit_token):03d}"
        rows.append(record)
    if not rows:
        raise ConfigurationError("An FD001 trajectory file has no rows.")
    return rows


def _parse_rul(text: str) -> tuple[str, ...]:
    """Read one official remaining-life token per test engine.

    Args:
        text: ``RUL_FD001.txt`` body.

    Returns:
        One token per non-blank line, in file order. These values are test
        truth for the last observation. They are not training labels.
    """
    return tuple(line.split()[0] for line in text.splitlines() if line.split())


def _write_official_rul(path: Path, asset_ids: Sequence[str], values: Sequence[str]) -> None:
    """Write asset id and official remaining life, one pair per line.

    Args:
        path: Destination text file.
        asset_ids: Official test engine ids, in unit order.
        values: ``RUL_FD001.txt`` tokens in the same order.
    """
    lines = [f"{asset_id} {value}" for asset_id, value in zip(asset_ids, values, strict=True)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _ordered_unit_ids(rows: Sequence[Mapping[str, str]]) -> tuple[str, ...]:
    """Return asset ids sorted by the numeric unit inside the id.

    Args:
        rows: Signal rows.

    Returns:
        Unique ids in unit-number order.
    """
    identifiers = {row["unit_id"] for row in rows}
    return tuple(sorted(identifiers, key=lambda asset_id: int(asset_id.rsplit("-", 1)[1])))


def _events(rows: Sequence[Mapping[str, str]], *, event_type: str) -> list[dict[str, str]]:
    """Build one close event at the last cycle of each engine.

    Args:
        rows: Signal rows for completed or censored engines.
        event_type: ``failure`` or ``censored``.

    Returns:
        Event rows.
    """
    last_cycle: dict[str, int] = {}
    for row in rows:
        cycle = int(row["cycle"])
        asset_id = row["unit_id"]
        if cycle > last_cycle.get(asset_id, -1):
            last_cycle[asset_id] = cycle
    return [
        {"unit_id": asset_id, "cycle": str(last_cycle[asset_id]), "event_type": event_type}
        for asset_id in sorted(last_cycle, key=lambda asset_id: int(asset_id.rsplit("-", 1)[1]))
    ]


def _write_ids(path: Path, identifiers: Sequence[str]) -> None:
    """Write one asset id per line.

    Args:
        path: Destination text file.
        identifiers: Ids in split order.
    """
    path.write_text("".join(f"{asset_id}\n" for asset_id in identifiers), encoding="utf-8")


def _write_parquet(path: Path, rows: Sequence[Mapping[str, str]]) -> None:
    """Write string columns to a Parquet file.

    Args:
        path: Destination path.
        rows: Rows that share the keys of the first row.

    Raises:
        ConfigurationError: pyarrow is missing or the table cannot be written.
    """
    if not rows:
        raise ConfigurationError(f"Refusing to write an empty table to {path.name}.")
    try:
        import pyarrow as arrow  # type: ignore[import-untyped]
        import pyarrow.parquet as parquet  # type: ignore[import-untyped]
    except ImportError as error:
        raise ConfigurationError("Writing Parquet requires pyarrow.") from error
    names = list(rows[0].keys())
    columns = {name: [row[name] for row in rows] for name in names}
    try:
        parquet.write_table(arrow.table(columns), path)
    except (OSError, ValueError, TypeError) as error:
        raise ConfigurationError(f"Could not write table file {path}.") from error
