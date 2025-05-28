import matplotlib.colors as colors

_cdict = {
    'red': (
        (0.0, 0.0, 0.0),
        (0.25, 0.0, 0.0),
        (0.5, 0.8, 1.0),
        (0.75, 1.0, 1.0),
        (1.0, 0.4, 1.0),
    ),
    'green': (
        (0.0, 0.0, 0.0),
        (0.25, 0.0, 0.0),
        (0.5, 0.9, 0.9),
        (0.75, 0.0, 0.0),
        (1.0, 0.0, 0.0),
    ),
    'blue': (
        (0.0, 0.0, 0.4),
        (0.25, 1.0, 1.0),
        (0.5, 1.0, 0.8),
        (0.75, 0.0, 0.0),
        (1.0, 0.0, 0.0),
    ),
    'alpha': (
        (0.0, 1.0, 1.0),
        (0.25, 1.0, 1.0),
        (0.5, 0.3, 0.3),
        (0.75, 1.0, 1.0),
        (1.0, 1.0, 1.0),
    ),
}
resid_cmap = colors.LinearSegmentedColormap("ResidualCmap", _cdict)
resid_norm = colors.SymLogNorm(linthresh=1e-6, linscale=1., vmin=-0.01, vmax=0.01)
abs_resid_norm = colors.LogNorm(vmin=1e-6, vmax=0.01)
