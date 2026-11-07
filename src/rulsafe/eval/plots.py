"""Plot images embedded in the HTML report.

v0.1 plots are prediction error, error by unit, and history dispositions.
Fleet plots may be requested. Until they exist, the report says they were
not produced.
"""

from rulsafe.config import PlotName
from rulsafe.exceptions import not_implemented


def render_plot(plot_name: PlotName) -> bytes:
    """Render one report plot as image bytes.

    Args:
        plot_name: Plot requested in the configuration.

    Returns:
        Image bytes suitable for embedding in a self-contained HTML file.

    Raises:
        NotImplementedError: Plotting is not implemented yet.
    """
    raise not_implemented("render_plot", plot_name)
