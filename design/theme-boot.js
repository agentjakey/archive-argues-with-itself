// Sets html[data-theme] to "light" or "dark" before the first paint, so a page never flashes the
// wrong theme. Loaded as a blocking script in the head of the reading room and the catalogue (the
// site's Content-Security-Policy allows no inline scripts). The visitor's choice, when they made one,
// is the single localStorage key "theme"; with no choice the page follows the device setting and
// keeps following it. Kiosk pages (?kiosk=1) never read or write it and stay dark.
(function () {
  var root = document.documentElement;
  var kiosk = /[?&]kiosk=1(&|$)/.test(window.location.search);
  var media = window.matchMedia ? window.matchMedia("(prefers-color-scheme: light)") : null;

  function saved() {
    if (kiosk) return null;
    try {
      var v = window.localStorage.getItem("theme");
      return v === "light" || v === "dark" ? v : null;
    } catch (e) {
      return null;
    }
  }

  function apply() {
    var theme = kiosk ? "dark" : saved() || (media && media.matches ? "light" : "dark");
    root.setAttribute("data-theme", theme);
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", theme === "light" ? "#f5efe1" : "#0e0c09");
    return theme;
  }

  // A choice equal to the device setting is not saved (and clears an earlier one), so a visitor who
  // switches back ends up following the device again, with nothing left in storage.
  function set(theme) {
    if (kiosk) return apply();
    var system = media && media.matches ? "light" : "dark";
    try {
      if (theme === system) window.localStorage.removeItem("theme");
      else window.localStorage.setItem("theme", theme);
    } catch (e) {
      root.setAttribute("data-theme", theme);
      return theme;
    }
    return apply();
  }

  apply();
  if (media && media.addEventListener) media.addEventListener("change", apply);
  window.archiveTheme = { apply: apply, saved: saved, set: set, kiosk: kiosk };
})();
