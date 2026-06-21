/* Modern, consistent emoji rendering across every OS/browser.
 *
 * Native emoji glyphs vary wildly (and look dated/"basic" on some Windows
 * and Linux builds). Twemoji replaces them with the latest colour SVG set so
 * PLAGENOR shows the same modern emoji everywhere. We re-parse on dynamic
 * updates (htmx swaps, and anything that calls window.twemojiParse).
 */
(function () {
    var BASE = 'https://cdn.jsdelivr.net/gh/jdecked/twemoji@15.1.0/assets/';

    function parse(node) {
        if (!window.twemoji) { return; }
        try {
            window.twemoji.parse(node || document.body, {
                folder: 'svg',
                ext: '.svg',
                base: BASE,
                className: 'emoji'
            });
        } catch (e) { /* offline / blocked CDN → keep native glyphs */ }
    }

    // Public helper so views that swap emoji text (e.g. the rating stars)
    // can re-render just their node.
    window.twemojiParse = parse;

    function init() { parse(document.body); }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // Re-render emoji injected by htmx partial swaps.
    document.addEventListener('htmx:afterSwap', function (e) {
        parse(e.target || document.body);
    });
})();
