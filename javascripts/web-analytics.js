(() => {
  const token = "99fdc53f239141b2ab42018d8d415461";
  if (location.hostname !== "zjusuee.github.io" || !/^[a-f0-9]{32}$/.test(token)) return;

  const load = () => {
    const beacon = document.createElement("script");
    beacon.type = "module";
    beacon.async = true;
    beacon.src = "https://static.cloudflareinsights.com/beacon.min.js";
    beacon.dataset.cfBeacon = JSON.stringify({ token });
    beacon.onerror = () => beacon.remove();
    document.head.appendChild(beacon);
  };

  // Keep the external request out of the page's initial loading path.
  if (document.readyState === "complete") load();
  else window.addEventListener("load", load, { once: true });
})();
