(() => {
    const header = document.querySelector('.site-header');
    if (!header) return;
    const inner = header.querySelector('.header-inner');
    const menu = header.querySelector('.site-menu');
    const toggle = header.querySelector('.menu-toggle');
    const brand = header.querySelector('.brand');
    const setOpen = open => {
        header.classList.toggle('is-open', open);
        toggle.setAttribute('aria-expanded', String(open));
    };
    const layout = () => {
        const wasWide = header.classList.contains('is-wide');
        header.classList.add('is-measuring');
        const needed = menu.scrollWidth + brand.getBoundingClientRect().width + 48;
        const wide = needed <= inner.clientWidth;
        header.classList.remove('is-measuring');
        header.classList.toggle('is-wide', wide);
        if (wide !== wasWide) {
            if (!wide && menu.contains(document.activeElement)) toggle.focus();
            if (wide && document.activeElement === toggle) menu.querySelector('a').focus();
            setOpen(false);
        }
    };
    toggle.hidden = false;
    header.classList.add('nav-ready');
    toggle.addEventListener('click', () => setOpen(toggle.getAttribute('aria-expanded') !== 'true'));
    header.addEventListener('keydown', event => {
        if (event.key === 'Escape' && header.classList.contains('is-open')) {
            setOpen(false);
            toggle.focus();
        }
    });
    layout();
    if ('ResizeObserver' in window) new ResizeObserver(layout).observe(inner);
    else window.addEventListener('resize', layout);
    document.fonts?.ready.then(layout);
})();
