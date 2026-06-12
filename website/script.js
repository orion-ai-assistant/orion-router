document.addEventListener('DOMContentLoaded', () => {

    // --- Scroll Animasyonları (Intersection Observer) ---
    const revealElements = document.querySelectorAll(".reveal");
    const revealObserver = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add("active");
                observer.unobserve(entry.target);
            }
        });
    }, {
        threshold: 0.1,
        rootMargin: "0px 0px -40px 0px"
    });

    revealElements.forEach(el => {
        revealObserver.observe(el);
    });

    // --- Tab / Sekme Değiştirme Mantığı ---
    const methodButtons = document.querySelectorAll('[data-method]');
    const osButtons = document.querySelectorAll('[data-os]');
    const codePanels = document.querySelectorAll('.code-content');
    
    let selectedMethod = 'docker'; // 'docker' veya 'local'
    let selectedOS = 'win'; // 'win' veya 'mac'

    function updateActivePanel() {
        // Tüm içeriklerin active sınıfını temizle
        codePanels.forEach(p => p.classList.remove('active'));
        // Doğru içeriği göster
        const targetPanelId = `${selectedOS}-${selectedMethod}-panel`;
        const targetPanel = document.getElementById(targetPanelId);
        if (targetPanel) {
            targetPanel.classList.add('active');
        }
    }

    methodButtons.forEach(btn => {
        btn.addEventListener('click', (e) => {
            selectedMethod = e.currentTarget.getAttribute('data-method');
            methodButtons.forEach(b => b.classList.remove('active'));
            e.currentTarget.classList.add('active');
            updateActivePanel();
        });
    });

    osButtons.forEach(btn => {
        btn.addEventListener('click', (e) => {
            selectedOS = e.currentTarget.getAttribute('data-os');
            osButtons.forEach(b => b.classList.remove('active'));
            e.currentTarget.classList.add('active');
            updateActivePanel();
        });
    });

    // --- Kopyala (Copy to Clipboard) Mantığı ---
    const commandDictionary = {
        'win-docker': 'powershell -c "iex(irm raw.github.com/krstalacam/orion-router/main/install.ps1)"',
        'mac-docker': 'curl -sL raw.github.com/krstalacam/orion-router/main/install.sh | bash',
        'win-local': 'powershell -c "&([scriptblock]::Create((irm raw.github.com/krstalacam/orion-router/main/install.ps1))) local"',
        'mac-local': 'curl -sL raw.github.com/krstalacam/orion-router/main/install.sh | bash -s local'
    };

    const copyBtn = document.getElementById('orion-cli-copy-action-button');
    const iconContainer = document.getElementById('copy-icon-container');

    // Standart kopyala butonu görünümü
    const defaultIconHTML = `
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width: 14px; height: 14px;">
            <path stroke-linecap="round" stroke-linejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"></path>
        </svg>
    `;

    // Kopyalandı (Success) görünümü
    const successIconHTML = `
        <svg viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="2" style="width: 14px; height: 14px;">
            <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
        </svg>
    `;

    copyBtn.addEventListener('click', () => {
        const textToCopy = commandDictionary[`${selectedOS}-${selectedMethod}`];

        navigator.clipboard.writeText(textToCopy).then(() => {
            // Görünümü değiştir
            iconContainer.innerHTML = successIconHTML;

            // 2.5 Saniye sonra eski haline geri getir (React Timeout gibi)
            setTimeout(() => {
                iconContainer.innerHTML = defaultIconHTML;
            }, 2500);
        }).catch(err => {
            console.error('Kopyalama işlemi başarısız:', err);
            // İsteğe bağlı: Kullanıcıya "Kopyalanamadı" şeklinde bir HTML bildirimi gösterebilirsin
        });
    });
});