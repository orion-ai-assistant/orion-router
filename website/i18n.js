(function() {
    // 1. Detect language (check browser settings, fallback to 'en')
    function detectLanguage() {
        const browserLang = (navigator.language || navigator.userLanguage).toLowerCase();
        if (browserLang.startsWith('tr')) {
            return 'tr';
        } else if (browserLang.startsWith('zh')) {
            return 'zh';
        } else {
            return 'en';
        }
    }

    window.ORION_CURRENT_LANG = detectLanguage();

    // 2. Translation function t(key)
    window.t = function(key) {
        if (typeof window.ORION_TRANSLATIONS === 'undefined') return key;
        const dict = window.ORION_TRANSLATIONS[window.ORION_CURRENT_LANG] || window.ORION_TRANSLATIONS['en'];
        const fallback = window.ORION_TRANSLATIONS['en'];
        return dict[key] !== undefined ? dict[key] : (fallback[key] !== undefined ? fallback[key] : key);
    };

    // 3. Set language and update DOM
    window.setLanguage = function(lang) {
        if (typeof window.ORION_TRANSLATIONS === 'undefined' || !window.ORION_TRANSLATIONS[lang]) return;

        window.ORION_CURRENT_LANG = lang;
        document.documentElement.lang = lang;

        // Translate all data-i18n elements
        const translateElements = document.querySelectorAll('[data-i18n]');
        translateElements.forEach(el => {
            const key = el.getAttribute('data-i18n');
            const value = window.t(key);
            if (value !== key) {
                el.innerHTML = value;
            }
        });

        // Trigger custom event to notify UI listeners (like dropdown switcher)
        document.dispatchEvent(new CustomEvent('orion-lang-changed', { detail: { lang } }));
    };

    // Auto translate DOM on load
    document.addEventListener('DOMContentLoaded', () => {
        window.setLanguage(window.ORION_CURRENT_LANG);
    });
})();
