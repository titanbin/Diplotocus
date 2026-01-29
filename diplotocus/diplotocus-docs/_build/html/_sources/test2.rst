Stellar model grids
===================

For convenience, various grids are provided in a format which is compatible with SPInS.

BaSTI grids
-----------

These grids come from the `BaSTI website <http://albione.oa-teramo.inaf.it/>`_ 
and are provided here with permission from S. Cassisi.  They include the following
quantities: age parameter, age, initial mass, luminosity, effective temperature, mass,
radius, Z, Y, [M/H], surface gravity, :math:`\Delta \nu`, :math:`\nu_{\mathrm{max}}`,
Mv, U-B, B-V, V-I, V-R, V-J, V-K, V-L, and H-K.  We note that the surface gravity, 
:math:`\Delta \nu`, and :math:`\nu_{\mathrm{max}}` have been derived from the mass, radius,
and effective temperature, using appropriate scaling relations, and the following
constants:

  * solar_radius     = 6.960e10  :math:`\mathrm{cm}`
  * solar_mass       = 1.98919e33 :math:`\mathrm{g}`
  * G = 6.671682343064262e-08 :math:`\mathrm{cm^3.g^{-1}.s^{-2}}`
  * solar_dnu        = 135.1 :math:`\mathrm{\mu Hz}`
  * solar_numax      = 3090.0 :math:`\mathrm{\mu Hz}`

+-----------------------------------------------+----------+----------+-------------------------------------------------------------------+
| Grid                                          | # tracks | # Models | Link                                                              |
+===============================================+==========+==========+===================================================================+
| BaSTI, scaled solar, canonical                | 490      | 885920   | `Download (100.8 MB) <https://share.obspm.fr/s/Gj7RSGeFAgFo5He>`_ |
+-----------------------------------------------+----------+----------+-------------------------------------------------------------------+
| BaSTI, scaled solar, non canonical            | 328      | 561920   | `Download  (64.8 MB) <https://share.obspm.fr/s/efEN4HszT5LBFez>`_ |
+-----------------------------------------------+----------+----------+-------------------------------------------------------------------+
| BaSTI, :math:`\alpha`-enhanced, canonical     | 469      | 850640   | `Download  (96.6 MB) <https://share.obspm.fr/s/EwyqY27x4D5ayPA>`_ |
+-----------------------------------------------+----------+----------+-------------------------------------------------------------------+
| BaSTI, :math:`\alpha`-enhanced, non canonical | 301      | 602000   | `Download  (68.6 MB) <https://share.obspm.fr/s/ECoMwaeHWcyrdyA>`_ |
+-----------------------------------------------+----------+----------+-------------------------------------------------------------------+

*Relevant references*

  * `Pietrinferni et al. (2004), ApJ 612, pp. 168-190. <https://ui.adsabs.harvard.edu/abs/2004ApJ...612..168P/abstract>`_
  * `Pietrinferni et al. (2006), ApJ 642, pp. 797-812. <https://ui.adsabs.harvard.edu/abs/2006ApJ...642..797P/abstract>`_
