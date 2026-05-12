// Navigation active link
const navLinks = document.querySelectorAll('.nav-link');
const sections = document.querySelectorAll('.section');

function updateActiveNav() {
    let current = '';
    const scrollY = window.scrollY + 100;

    sections.forEach(section => {
        const top = section.offsetTop;
        const bottom = top + section.offsetHeight;
        if (scrollY >= top && scrollY < bottom) {
            current = section.getAttribute('id');
        }
    });

    navLinks.forEach(link => {
        link.classList.remove('active');
        if (link.getAttribute('href') === `#${current}`) {
            link.classList.add('active');
        }
    });
}

window.addEventListener('scroll', updateActiveNav);
window.addEventListener('load', updateActiveNav);

// Smooth scroll
navLinks.forEach(link => {
    link.addEventListener('click', (e) => {
        const href = link.getAttribute('href');
        if (href.startsWith('#')) {
            e.preventDefault();
            const target = document.querySelector(href);
            if (target) {
                const navHeight = document.querySelector('.navbar').offsetHeight;
                window.scrollTo({
                    top: target.offsetTop - navHeight,
                    behavior: 'smooth'
                });
            }
        }
    });
});