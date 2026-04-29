function setTheme(mode) {
  document.body.dataset.theme = mode;
  localStorage.setItem("theme", mode);
}
setTheme('light');