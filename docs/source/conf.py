# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import os
import sys
import inspect
import diplotocus
from diplotocus._version import __version__
sys.path.insert(0, os.path.abspath("../../src"))

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'diplotocus'
copyright = '2026, Tristan Boin'
author = 'Tristan Boin'
release = __version__
version = __version__

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

def linkcode_resolve(domain, info):
    if domain != "py":
        return None
    if not info["module"]:
        return None

    try:
        module = __import__(info["module"], fromlist=[""])
        obj = module
        for part in info["fullname"].split("."):
            obj = getattr(obj, part)

        fn = inspect.getsourcefile(obj)
        source, lineno = inspect.getsourcelines(obj)
    except Exception:
        return None

    # Path relative to your package root (inside src/)
    pkg_dir = os.path.dirname(diplotocus.__file__)
    relpath = os.path.relpath(fn, start=pkg_dir)

    return f"https://github.com/titanbin/Diplotocus/blob/main/src/diplotocus/{relpath}#L{lineno}"

extensions = [
    "myst_nb",
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.linkcode",
    "sphinx.ext.intersphinx",
    "sphinx_autodoc_typehints",
    "sphinx_copybutton"
]

intersphinx_mapping = {
    "matplotlib": ("https://matplotlib.org/stable", "https://matplotlib.org/stable/objects.inv"),
}

myst_heading_anchors = 0
myst_all_links_external = True

templates_path = ['_templates']
# exclude specific generated/unused notebooks to avoid spurious warnings
exclude_patterns = [
    'notebooks/logo.ipynb','notebooks/index.ipynb'
]

html_favicon = "_static/favicon.ico"

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "furo"
html_static_path = ["_static"]
html_theme_options = {
    "sidebar_hide_name": True,
}
pygments_style = "manni"

# Force site logo and light mode; include assets that force light theme and hide the
# theme switcher so the site remains white-only.
html_logo = "_static/logo.svg"
html_css_files = [
    'force-light.css',
]
html_js_files = [
    'force-light.js',
]

myst_enable_extensions = [
    "html_image",
    "dollarmath",
]

nb_execution_allow_errors = True
nb_execution_mode = "off"