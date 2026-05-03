(function enforceLight() {
  function setLight() {
    try {
      // prefer setting the document element attribute used by themes
      document.documentElement.setAttribute('data-theme', 'light');
      if (document.body) document.body.dataset.theme = 'light';
      localStorage.setItem('theme', 'light');

      // hide common theme toggle controls if present
      var selectors = [
        '.theme-toggle',
        '.toggle-color-mode',
        '.toggle-theme',
        '.sd-theme-toggle',
        'button[aria-label^="Toggle color"], button[aria-label*="theme"]'
      ];
      selectors.forEach(function(s) {
        var el = document.querySelector(s);
        if (el) el.style.display = 'none';
      });
    } catch (e) {
      // ignore
    }
  }

  setLight();
  window.addEventListener('DOMContentLoaded', setLight);
  window.addEventListener('load', setLight);
  // Enforce repeatedly for a short while in case other scripts override
  var tries = 0;
  var id = setInterval(function() {
    setLight();
    tries += 1;
    if (tries > 20) clearInterval(id);
  }, 200);
})();