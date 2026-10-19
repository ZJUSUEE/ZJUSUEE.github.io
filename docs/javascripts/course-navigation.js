(() => {
  const menus = [...document.querySelectorAll('.site-direction-menu')];
  for (const menu of menus) {
    menu.querySelector('summary').addEventListener('click', event => {
      // A mouse click follows hover; keep the menu open instead of toggling it shut.
      if (event.detail > 0) {
        event.preventDefault();
        menu.open = true;
      }
    });
    menu.addEventListener('pointerenter', event => {
      if (event.pointerType === 'mouse') menu.open = true;
    });
    menu.addEventListener('pointerleave', () => {
      if (!menu.contains(document.activeElement)) menu.open = false;
    });
    menu.addEventListener('focusout', event => {
      if (!menu.contains(event.relatedTarget)) menu.open = false;
    });
    menu.addEventListener('keydown', event => {
      if (event.key === 'Escape') {
        menu.open = false;
        menu.querySelector('summary').focus();
      }
    });
    menu.addEventListener('toggle', () => {
      if (menu.open) for (const other of menus) if (other !== menu) other.open = false;
    });
  }
  document.addEventListener('click', event => {
    for (const menu of menus) if (!menu.contains(event.target)) menu.open = false;
  });
})();
