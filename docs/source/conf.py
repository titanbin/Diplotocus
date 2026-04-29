# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import os
import sys
sys.path.insert(0, os.path.abspath("../../src"))

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'diplotocus'
copyright = '2026, Tristan Boin'
author = 'Tristan Boin'
release = '2026'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "myst_nb",
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx_autodoc_typehints"
]

templates_path = ['_templates']
# exclude specific generated/unused notebooks to avoid spurious warnings
exclude_patterns = [
    'notebooks/logo.ipynb','notebooks/index.ipynb'
]

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "furo"
html_static_path = ["_static"]
html_theme_options = {
    "sidebar_hide_name": True,
}

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