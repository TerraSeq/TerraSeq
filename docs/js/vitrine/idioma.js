// Vitrine (docs/index.html) -- seletor de idioma
// Faz parte da reorganização 2.0; ordem de carregamento em docs/index.html.

// ---- Seletor de idioma (PT/EN) ----
// Traduz apenas a interface (menus, títulos, botões, placeholders).
// Os dados de cada requisição (nome do primer, banco, sequências) vêm
// prontos do pipeline em português/nomenclatura científica e não são
// traduzidos -- só valores fixos e controlados (status "Concluído",
// botão "Ver Relatório") entram no mapa TERMOS_FIXOS_PT_EN (traducoes.js).
let idiomaAtual = "en";
// Chave nova (v2): a antiga era gravada automaticamente com "pt" na
// primeira visita, o que prenderia quem já visitou o site no padrão
// antigo mesmo sem nunca ter escolhido o idioma.
const CHAVE_IDIOMA = "terraseq-lang-v2";

// Formato de número/data do idioma atual (ex.: 4.293 em PT, 4,293 em EN).
function localeAtual() { return idiomaAtual === "en" ? "en-US" : "pt-BR"; }

function t(chave) {
    return (DICIONARIO[idiomaAtual] && DICIONARIO[idiomaAtual][chave]) || chave;
}

function aplicarIdioma(lang) {
    idiomaAtual = lang;

    document.querySelectorAll("[data-i18n]").forEach(el => {
        const texto = DICIONARIO[lang][el.getAttribute("data-i18n")];
        if (texto !== undefined) el.innerHTML = texto;
    });
    document.querySelectorAll("[data-i18n-placeholder]").forEach(el => {
        const texto = DICIONARIO[lang][el.getAttribute("data-i18n-placeholder")];
        if (texto !== undefined) el.placeholder = texto;
    });

    const mapaFixo = lang === "en" ? TERMOS_FIXOS_PT_EN : TERMOS_FIXOS_EN_PT;
    document.querySelectorAll("#results-body .status-badge, #results-body .btn-primary").forEach(el => {
        const atual = el.textContent.trim();
        if (mapaFixo[atual]) el.textContent = mapaFixo[atual];
    });

    document.querySelectorAll("[data-lang-btn]").forEach(btn => {
        btn.classList.toggle("active", btn.dataset.langBtn === lang);
    });
    document.documentElement.setAttribute("lang", lang);
    document.title = DICIONARIO[lang]["pagina.titulo"];

    // Avisa as partes montadas via JS (tabela, acervo) para refazerem os
    // próprios textos. Cada uma escuta "idioma-alterado" depois de se
    // inicializar, então antes disso o aviso simplesmente não tem ouvinte.
    document.dispatchEvent(new Event("idioma-alterado"));
}

document.addEventListener("DOMContentLoaded", function() {
    document.querySelectorAll("[data-lang-btn]").forEach(btn => {
        btn.addEventListener("click", () => {
            aplicarIdioma(btn.dataset.langBtn);
            // Só guarda a escolha quando o visitante clica no seletor;
            // sem escolha explícita, vale o padrão (inglês).
            try { localStorage.setItem(CHAVE_IDIOMA, btn.dataset.langBtn); } catch (e) {}
        });
    });

    let idiomaInicial = "en";
    try {
        const salvo = localStorage.getItem(CHAVE_IDIOMA);
        if (salvo === "pt" || salvo === "en") idiomaInicial = salvo;
    } catch (e) {}
    aplicarIdioma(idiomaInicial);
});
