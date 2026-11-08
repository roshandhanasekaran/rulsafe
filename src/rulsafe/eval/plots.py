"""Reserved plot-rendering interface.

The v0.1 public pipeline does not call this module or render plot images.
"""

from rulsafe.config import PlotName
from rulsafe.exceptions import not_implemented


def render_plot(plot_name: PlotName) -> bytes:
    """Reserved entry point for future report plots.

    Args:
        plot_name: Plot requested in the configuration.

    Returns:
        Image bytes suitable for embedding in a self-contained HTML file.

    Raises:
        NotImplementedError: Plot rendering is not implemented.
    """
    raise not_implemented("render_plot", plot_name)
