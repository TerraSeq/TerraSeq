// Comportamento da vitrine (docs/index.html): idioma PT/EN, tabela de análises,
// carrossel e painel do acervo de genomas.
// Separado do HTML na reorganização 2.0; o conteúdo é o mesmo da versão 1.0.
// Carregado no fim do <body>, então o HTML já existe quando este arquivo roda.

// ---- Seletor de idioma (PT/EN) ----
// Traduz apenas a interface (menus, títulos, botões, placeholders).
// Os dados de cada requisição (nome do primer, banco, sequências) vêm
// prontos do pipeline em português/nomenclatura científica e não são
// traduzidos -- só valores fixos e controlados (status "Concluído",
// botão "Ver Relatório") entram no mapa de termos fixos abaixo.
let idiomaAtual = "en";
// Chave nova (v2): a antiga era gravada automaticamente com "pt" na
// primeira visita, o que prenderia quem já visitou o site no padrão
// antigo mesmo sem nunca ter escolhido o idioma.
const CHAVE_IDIOMA = "terraseq-lang-v2";

const DICIONARIO = {
    pt: {
        "pagina.titulo": "TerraSeq | Validação de Primers",
        "nav.inicio": "Início",
        "nav.submeter": "Testar Primer",
        "nav.acervo": "Acervo de Genomas",
        "nav.resultados": "Resultados",
        "nav.sobre": "Equipe & Sobre",
        "hero.titulo": "Validação <em>in silico</em> de Primers",
        "hero.sub": "Uma plataforma automatizada para avaliação de cobertura taxonômica e simulação de PCR contra genomas completos.",
        "submeter.titulo": "Escolha sua via de Submissão",
        "submeter.intro": "O nosso pipeline suporta duas arquiteturas diferentes para recebimento e processamento de ensaios.",
        "submeter.forms.texto": "Preencha um formulário web simples e receba os resultados diretamente no seu e-mail.",
        "submeter.forms.btn": "Formulário de Análise",
        "submeter.issues.texto": "Submeta seus parâmetros via Issues e acompanhe o log de execução público.",
        "submeter.issues.btn": "Abrir Nova Issue",
        "acervo.titulo": "Acervo de Genomas",
        "acervo.foto": "Foto",
        "acervo.recortada": "recortada",
        "acervo.intro": "Os bancos de referência curados que sustentam cada busca <em>in silico</em> da TerraSeq — organizados pelos mesmos grupos taxonômicos do Atlas Global da Biodiversidade do Solo.",
        "acervo.carregando": "Carregando acervo...",
        "acervo.indisponivel": "Acervo em atualização — volte em breve.",
        "acervo.hint": "Passe o mouse pra pausar · arraste pra rolar · clique num banco pra ver os organismos catalogados",
        "acervo.fechar": "Fechar ✕",
        "acervo.buscarPlaceholder": "Buscar organismo neste banco...",
        "acervo.semOrganismo": "Nenhum organismo encontrado.",
        "acervo.statBancos": "bancos curados",
        "acervo.statGenomas": "genomas catalogados",
        "acervo.genomasLabel": "genomas",
        "resultados.titulo": "Acervo de Primers Avaliados",
        "resultados.intro": "Histórico de análises já processadas e validadas pelo pipeline contra nossos bancos de genomas de referência.",
        "resultados.buscarPlaceholder": "Buscar por ID, nome do primer, alvo ou sequência...",
        "resultados.todosBancos": "Todos os bancos",
        "resultados.todosAlvos": "Todos os alvos",
        "resultados.limparFiltros": "Limpar filtros",
        "resultados.porPagina": "Resultados por página:",
        "resultados.todos": "Todos",
        "resultados.vazio": "Nenhuma análise publicada ainda. Novos relatórios aparecerão aqui assim que forem concluídos.",
        "resultados.de": "de",
        "resultados.resultadosSufixo": "resultado(s)",
        "tabela.id": "ID da Requisição",
        "tabela.nome": "Nome do Par de Primers",
        "tabela.alvo": "Alvo",
        "tabela.banco": "Banco",
        "tabela.primers": "Primers (5'→3')",
        "tabela.amplicon": "Tamanho do Amplicon",
        "tabela.data": "Data",
        "tabela.status": "Status",
        "tabela.acao": "Ação",
        "sobre.titulo": "Sobre o Projeto",
        "sobre.intro": "Conheça a equipe de pesquisa e as instituições que apoiam a plataforma.",
        "sobre.nossaEquipe": "Nossa Equipe",
        "sobre.perfilLink": "Sobre ↗",
        "sobre.semFoto": "NO PHOTO",
        "sobre.cargo.tiago": "Desenvolvedor / Pesquisador",
        "sobre.cargo.leandro": "Pesquisador / Orientador",
        "sobre.cargo.liana": "Pesquisadora / Coordenadora",
        "sobre.cargo.eliezer": "Pesquisador Colaborador",
        "sobre.cargo.thierry": "Colaborador",
        "sobre.institEnvolvidas": "Instituições Envolvidas",
        "sobre.institExecutora": "Instituição Executora",
        "sobre.institColaboradoras": "Instituições Colaboradoras",
        "sobre.agenciasFomento": "Agências de Fomento (Apoio)",
        "sobre.projeto": "Projeto:",
        "sobre.coordenador": "Coordenador:",
        "sobre.coordenadora": "Coordenadora:"
    },
    en: {
        "pagina.titulo": "TerraSeq | Primer Validation",
        "nav.inicio": "Home",
        "nav.submeter": "Test a Primer",
        "nav.acervo": "Genome Archive",
        "nav.resultados": "Results",
        "nav.sobre": "Team & About",
        "hero.titulo": "<em>In Silico</em> Primer Validation",
        "hero.sub": "An automated platform for taxonomic coverage assessment and PCR simulation against complete genomes.",
        "submeter.titulo": "Choose Your Submission Method",
        "submeter.intro": "Our pipeline supports two different architectures for receiving and processing assays.",
        "submeter.forms.texto": "Fill out a simple web form and get your results straight to your inbox.",
        "submeter.forms.btn": "Analysis Form",
        "submeter.issues.texto": "Submit your parameters via Issues and follow the public execution log.",
        "submeter.issues.btn": "Open New Issue",
        "acervo.titulo": "Genome Archive",
        "acervo.foto": "Photo",
        "acervo.recortada": "cropped",
        "acervo.intro": "The curated reference databases behind every <em>in silico</em> search on TerraSeq — organized by the same taxonomic groups as the Global Soil Biodiversity Atlas.",
        "acervo.carregando": "Loading archive...",
        "acervo.indisponivel": "Archive being updated — check back soon.",
        "acervo.hint": "Hover to pause · drag to scroll · click a database to see its catalogued organisms",
        "acervo.fechar": "Close ✕",
        "acervo.buscarPlaceholder": "Search organisms in this database...",
        "acervo.semOrganismo": "No organisms found.",
        "acervo.statBancos": "curated databases",
        "acervo.statGenomas": "catalogued genomes",
        "acervo.genomasLabel": "genomes",
        "resultados.titulo": "Evaluated Primer Archive",
        "resultados.intro": "History of analyses already processed and validated by the pipeline against our reference genome databases.",
        "resultados.buscarPlaceholder": "Search by ID, primer name, target or sequence...",
        "resultados.todosBancos": "All databases",
        "resultados.todosAlvos": "All targets",
        "resultados.limparFiltros": "Clear filters",
        "resultados.porPagina": "Results per page:",
        "resultados.todos": "All",
        "resultados.vazio": "No analyses published yet. New reports will appear here as soon as they are completed.",
        "resultados.de": "of",
        "resultados.resultadosSufixo": "result(s)",
        "tabela.id": "Request ID",
        "tabela.nome": "Primer Pair Name",
        "tabela.alvo": "Target",
        "tabela.banco": "Database",
        "tabela.primers": "Primers (5'→3')",
        "tabela.amplicon": "Amplicon Size",
        "tabela.data": "Date",
        "tabela.status": "Status",
        "tabela.acao": "Action",
        "sobre.titulo": "About the Project",
        "sobre.intro": "Meet the research team and the institutions that support the platform.",
        "sobre.nossaEquipe": "Our Team",
        "sobre.perfilLink": "About ↗",
        "sobre.semFoto": "NO PHOTO",
        "sobre.cargo.tiago": "Developer / Researcher",
        "sobre.cargo.leandro": "Researcher / Advisor",
        "sobre.cargo.liana": "Researcher / Coordinator",
        "sobre.cargo.eliezer": "Collaborating Researcher",
        "sobre.cargo.thierry": "Collaborator",
        "sobre.institEnvolvidas": "Institutions Involved",
        "sobre.institExecutora": "Lead Institution",
        "sobre.institColaboradoras": "Collaborating Institutions",
        "sobre.agenciasFomento": "Funding Agencies (Support)",
        "sobre.projeto": "Project:",
        "sobre.coordenador": "Coordinator:",
        "sobre.coordenadora": "Coordinator:"
    }
};

// Termos de vocabulário fixo (não são "texto livre") que aparecem
// repetidos em cada linha da tabela de resultados -- traduzidos por
// correspondência de valor em vez de um data-i18n por linha, assim
// cobre tanto as linhas existentes quanto as que main.py for
// adicionando no futuro sem precisar mexer no pipeline.
const TERMOS_FIXOS_PT_EN = {
    "Concluído": "Completed",
    "Ver Relatório": "View Report"
};
const TERMOS_FIXOS_EN_PT = Object.fromEntries(
    Object.entries(TERMOS_FIXOS_PT_EN).map(([pt, en]) => [en, pt])
);

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

    // Reaplica as partes que são montadas dinamicamente via JS
    // (dependem dos dados já terem carregado -- os hooks só existem
    // depois que cada seção terminou sua própria inicialização).
    if (typeof window._atualizarTextosAcervo === "function") window._atualizarTextosAcervo();
    if (typeof window._refrescarTabelaResultados === "function") window._refrescarTabelaResultados();
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

document.addEventListener("DOMContentLoaded", function() {
    const tableBody = document.getElementById("results-body");
    if (!tableBody) return;

    let rows = Array.from(tableBody.querySelectorAll("tr"));
    let filteredRows = rows.slice();

    const pageSizeSelect = document.getElementById("page-size-select");
    const searchInput = document.getElementById("filter-search");
    const bancoSelect = document.getElementById("filter-banco");
    const alvoSelect = document.getElementById("filter-alvo");
    const clearBtn = document.getElementById("filter-clear-btn");
    const resultCount = document.getElementById("filter-result-count");

    let rowsPerPage = 10;
    let currentPage = 1;
    let sortKey = "amplicon";
    let sortDir = "desc";

    // Índice da coluna (0-based) correspondente a cada chave ordenável
    const COLUMN_INDEX = { primername: 0, alvo: 1, banco: 2, date: 5, id: 8 };

    function getSortValue(row, key, type) {
        if (key === "amplicon") {
            return parseFloat(row.dataset.amplicon) || 0;
        }
        if (key === "date") {
            return row.dataset.date || "";
        }
        const cell = row.children[COLUMN_INDEX[key]];
        const text = cell ? cell.textContent.trim().toLowerCase() : "";
        return type === "number" ? (parseFloat(text) || 0) : text;
    }

    function sortRows(key, type) {
        const dir = sortDir === "asc" ? 1 : -1;
        rows.sort((a, b) => {
            const va = getSortValue(a, key, type);
            const vb = getSortValue(b, key, type);
            if (va < vb) return -1 * dir;
            if (va > vb) return 1 * dir;
            return 0;
        });
        rows.forEach(row => tableBody.appendChild(row));
    }

    function updateSortHeadersUI() {
        document.querySelectorAll(".results-table th.sortable").forEach(th => {
            th.classList.remove("sort-asc", "sort-desc");
            if (th.dataset.sortKey === sortKey) {
                th.classList.add(sortDir === "asc" ? "sort-asc" : "sort-desc");
            }
        });
    }

    // --- Popula os selects de filtro (Banco / Alvo) com os valores presentes na tabela ---
    function popularSelect(select, colIndex) {
        const valores = new Set();
        rows.forEach(row => {
            const cell = row.children[colIndex];
            const texto = cell ? cell.textContent.trim() : "";
            if (texto) valores.add(texto);
        });
        Array.from(valores).sort((a, b) => a.localeCompare(b, 'pt-BR')).forEach(valor => {
            const opt = document.createElement("option");
            opt.value = valor;
            opt.textContent = valor;
            select.appendChild(opt);
        });
    }
    if (bancoSelect) popularSelect(bancoSelect, COLUMN_INDEX.banco);
    if (alvoSelect) popularSelect(alvoSelect, COLUMN_INDEX.alvo);

    // --- Filtro: busca livre (ID, nome, alvo, banco, sequência) + banco + alvo ---
    function aplicarFiltro() {
        const termo = ((searchInput && searchInput.value) || "").trim().toLowerCase();
        const banco = bancoSelect ? bancoSelect.value : "";
        const alvo = alvoSelect ? alvoSelect.value : "";

        filteredRows = rows.filter(row => {
            if (banco && row.children[COLUMN_INDEX.banco].textContent.trim() !== banco) return false;
            if (alvo && row.children[COLUMN_INDEX.alvo].textContent.trim() !== alvo) return false;
            if (termo && !row.textContent.toLowerCase().includes(termo)) return false;
            return true;
        });

        rows.forEach(row => {
            if (!filteredRows.includes(row)) row.style.display = "none";
        });

        if (resultCount) {
            resultCount.textContent = filteredRows.length === rows.length
                ? `${rows.length} ${t('resultados.resultadosSufixo')}`
                : `${filteredRows.length} ${t('resultados.de')} ${rows.length} ${t('resultados.resultadosSufixo')}`;
        }

        currentPage = 1;
        displayRows(currentPage);
        setupPagination();
    }

    if (searchInput) searchInput.addEventListener("input", aplicarFiltro);
    if (bancoSelect) bancoSelect.addEventListener("change", aplicarFiltro);
    if (alvoSelect) alvoSelect.addEventListener("change", aplicarFiltro);
    if (clearBtn) clearBtn.addEventListener("click", function() {
        if (searchInput) searchInput.value = "";
        if (bancoSelect) bancoSelect.value = "";
        if (alvoSelect) alvoSelect.value = "";
        aplicarFiltro();
    });

    function displayRows(page) {
        const total = filteredRows.length;
        const perPage = rowsPerPage === "all" ? total : rowsPerPage;
        const start = (page - 1) * perPage;
        const end = start + perPage;

        filteredRows.forEach((row, index) => {
            row.style.display = index >= start && index < end ? "" : "none";
        });
    }

    function updatePaginationInfo() {
        const infoText = document.getElementById("page-info-text");
        if (!infoText) return;

        const total = filteredRows.length;
        const perPage = rowsPerPage === "all" ? total : rowsPerPage;
        const start = total === 0 ? 0 : (currentPage - 1) * perPage + 1;
        const end = Math.min(currentPage * perPage, total);
        infoText.innerText = `${start} - ${end} ${t('resultados.de')} ${total}`;
    }

    function updatePaginationUI() {
        const buttons = document.querySelectorAll("#pagination-container .page-btn:not(.arrow)");
        buttons.forEach(btn => {
            btn.classList.toggle("active", parseInt(btn.innerText) === currentPage);
        });
        updatePaginationInfo();
    }

    function getTotalPages() {
        const perPage = rowsPerPage === "all" ? filteredRows.length : rowsPerPage;
        return Math.max(1, Math.ceil(filteredRows.length / perPage));
    }

    function setupPagination() {
        const paginationContainer = document.getElementById("pagination-container");
        if (!paginationContainer) return;

        paginationContainer.innerHTML = "";
        const totalPages = getTotalPages();

        for (let i = 1; i <= totalPages; i++) {
            const btn = document.createElement("button");
            btn.classList.add("page-btn");
            if (i === currentPage) btn.classList.add("active");
            btn.innerText = i;

            btn.addEventListener("click", function() {
                currentPage = i;
                displayRows(currentPage);
                updatePaginationUI();
            });

            paginationContainer.appendChild(btn);
        }

        const nextBtn = document.createElement("button");
        nextBtn.classList.add("page-btn", "arrow");
        nextBtn.innerHTML = "❯";
        nextBtn.addEventListener("click", function() {
            if (currentPage < totalPages) {
                currentPage++;
                displayRows(currentPage);
                updatePaginationUI();
            }
        });
        paginationContainer.appendChild(nextBtn);

        const infoDiv = document.createElement("div");
        infoDiv.classList.add("page-info");
        infoDiv.id = "page-info-text";
        paginationContainer.appendChild(infoDiv);

        updatePaginationInfo();
    }

    function refreshTable() {
        currentPage = 1;
        displayRows(currentPage);
        setupPagination();
    }

    // --- Ajusta cada coluna pra largura que cabe o texto numa linha só ---
    // Força "não quebrar linha" temporariamente em cabeçalho e células
    // (só assim dá pra medir a largura "sem quebra" de verdade -- só
    // trocar pra table-layout:auto não é suficiente, o navegador ainda
    // prefere quebrar linha em vez de esticar a tabela), mede a largura
    // que cada coluna precisaria, trava esses valores em px no colgroup
    // e volta pro table-layout:fixed -- assim já nasce "esticada" e o
    // usuário ainda pode encolher arrastando (resize já existente).
    function autoAjustarLargurasColunas() {
        const table = document.querySelector(".results-table");
        if (!table) return;
        const cols = table.querySelectorAll("colgroup col");
        const ths = table.querySelectorAll("thead th");
        const celulas = table.querySelectorAll("tbody td");

        const layoutOriginalTabela = table.style.tableLayout;
        const minLarguraOriginal = table.style.minWidth;

        table.style.tableLayout = "auto";
        table.style.width = "auto";
        table.style.minWidth = "0";
        cols.forEach(c => { c.style.width = ""; });
        ths.forEach(th => { th.style.whiteSpace = "nowrap"; });
        celulas.forEach(td => { td.style.whiteSpace = "nowrap"; });

        void table.offsetWidth; // força recálculo de layout

        ths.forEach((th, i) => {
            if (!cols[i]) return;
            const largura = Math.ceil(th.getBoundingClientRect().width) + 6;
            cols[i].style.width = largura + "px";
        });

        ths.forEach(th => { th.style.whiteSpace = ""; });
        celulas.forEach(td => { td.style.whiteSpace = ""; });

        let total = 0;
        cols.forEach(c => total += parseFloat(c.style.width) || 0);

        table.style.tableLayout = layoutOriginalTabela || "fixed";
        table.style.width = total + "px";
        table.style.minWidth = minLarguraOriginal || "";
    }

    // --- Ordenação por clique no cabeçalho ---
    document.querySelectorAll(".results-table th.sortable").forEach(th => {
        th.addEventListener("click", function(e) {
            if (e.target.classList.contains("col-resizer")) return;
            const key = th.dataset.sortKey;
            const type = th.dataset.sortType;
            if (sortKey === key) {
                sortDir = sortDir === "asc" ? "desc" : "asc";
            } else {
                sortKey = key;
                sortDir = type === "number" ? "desc" : "asc";
            }
            sortRows(sortKey, type);
            updateSortHeadersUI();
            aplicarFiltro();
        });
    });

    // --- Controle de "Resultados por página" ---
    if (pageSizeSelect) {
        pageSizeSelect.addEventListener("change", function() {
            rowsPerPage = pageSizeSelect.value === "all" ? "all" : parseInt(pageSizeSelect.value);
            refreshTable();
        });
    }

    // Permite que o seletor de idioma reaplique a contagem de
    // resultados e o texto da paginação (que são montados via JS)
    // quando o idioma muda, sem precisar duplicar essa lógica.
    window._refrescarTabelaResultados = aplicarFiltro;

    const avisoVazio = document.getElementById("results-empty");
    if (avisoVazio) avisoVazio.style.display = rows.length === 0 ? "" : "none";

    if (rows.length > 0) {
        // Rankeia inicialmente pelos maiores amplicons
        sortRows(sortKey, "number");
        updateSortHeadersUI();
        autoAjustarLargurasColunas();
        aplicarFiltro();
    }

    // --- Redimensionar colunas por arraste (a largura muda e o texto reflui/quebra junto) ---
    (function setupColumnResize() {
        const table = document.querySelector(".results-table");
        if (!table) return;
        const cols = table.querySelectorAll("colgroup col");
        const ths = table.querySelectorAll("thead th");
        let resizing = null;

        function travarLargurasEmPixel() {
            let total = 0;
            ths.forEach((th, i) => {
                const w = th.getBoundingClientRect().width;
                total += w;
                if (cols[i]) cols[i].style.width = w + "px";
            });
            table.style.width = total + "px";
        }

        ths.forEach((th, i) => {
            const resizer = th.querySelector(".col-resizer");
            if (!resizer || !cols[i]) return;
            resizer.addEventListener("mousedown", function(e) {
                e.preventDefault();
                e.stopPropagation();
                travarLargurasEmPixel();
                resizing = { col: cols[i], startX: e.clientX, startWidth: parseFloat(cols[i].style.width) };
                resizer.classList.add("resizing");
                document.body.style.cursor = "col-resize";
            });
        });

        document.addEventListener("mousemove", function(e) {
            if (!resizing) return;
            const delta = e.clientX - resizing.startX;
            const newWidth = Math.max(50, resizing.startWidth + delta);
            resizing.col.style.width = newWidth + "px";
            let total = 0;
            cols.forEach(c => total += parseFloat(c.style.width) || 0);
            table.style.width = total + "px";
        });

        document.addEventListener("mouseup", function() {
            if (resizing) {
                document.querySelectorAll(".col-resizer.resizing").forEach(r => r.classList.remove("resizing"));
                resizing = null;
                document.body.style.cursor = "";
            }
        });
    })();
});

// ---- Acervo de Genomas: carrossel de bancos + busca de organismos ----
// Dados vêm de dados/acervo_genomas.json (scripts_auxiliares/
// exportar_acervo_genomas.py), já descontando a curadoria de habitat --
// só o que realmente está no banco de busca aparece aqui.
document.addEventListener("DOMContentLoaded", function() {
    const track = document.getElementById("acervo-carousel-track");
    const statLine = document.getElementById("acervo-stat-line");
    if (!track) return;

    function localeAtual() { return idiomaAtual === "en" ? "en-US" : "pt-BR"; }

    let dadosAcervo = null;
    let bancoAberto = null;

    fetch("dados/acervo_genomas.json")
        .then(r => { if (!r.ok) throw new Error("acervo indisponível"); return r.json(); })
        .then(dados => montarAcervo(dados))
        .catch(() => {
            statLine.textContent = t("acervo.indisponivel");
        });

    // Reaplica só os textos que dependem do idioma nas partes já
    // montadas (contadores, rótulos "genomas", painel aberto) sem
    // precisar reconstruir o carrossel inteiro.
    function atualizarTextosAcervo() {
        if (!dadosAcervo) return;
        statLine.textContent = `${dadosAcervo.total_bancos} ${t('acervo.statBancos')} · ${dadosAcervo.total_genomas.toLocaleString(localeAtual())} ${t('acervo.statGenomas')}`;

        document.querySelectorAll(".banco-chip").forEach(chip => {
            const genomas = parseInt(chip.dataset.genomas, 10) || 0;
            const contagemEl = chip.querySelector(".contagem");
            const labelEl = chip.querySelector(".genomas-label");
            if (contagemEl) contagemEl.textContent = genomas.toLocaleString(localeAtual());
            if (labelEl) labelEl.textContent = t("acervo.genomasLabel");
        });

        if (bancoAberto) {
            painelContagem.textContent = `${bancoAberto.genomas.toLocaleString(localeAtual())} ${t('acervo.genomasLabel')}`;
            renderLista(organismosAtuais.filter(n => n.toLowerCase().includes(buscaEl.value.toLowerCase().trim())));
        }
    }
    window._atualizarTextosAcervo = atualizarTextosAcervo;

    const painel = document.getElementById("painel-banco");
    const painelNome = document.getElementById("painel-nome");
    const painelContagem = document.getElementById("painel-contagem");
    const listaEl = document.getElementById("lista-organismos");
    const buscaEl = document.getElementById("busca-organismo");
    let organismosAtuais = [];

    // Pagina do Global Soil Biodiversity Atlas de onde veio a imagem de cada grupo.
    const LICENCA_CC_BY_SA_3 = "https://creativecommons.org/licenses/by-sa/3.0/";
    const FONTE_EXTRA = {
        platyhelminthes: { texto: "José Grau de Puerto Montt, CC BY-SA 3.0, via Wikimedia Commons", especie: "Obama burmeisteri", arquivo: "https://commons.wikimedia.org/wiki/File:Geoplana_burmeisteri.jpg", autor: "José Grau de Puerto Montt" },
        discoba: { texto: "Deuterostome, CC BY-SA 3.0, via Wikimedia Commons", especie: "Euglena sp.", arquivo: "https://commons.wikimedia.org/wiki/File:Euglena_sp.jpg", autor: "Deuterostome" },
    };
    // Fotografo(s) de cada imagem, como listado na pagina 3 do Atlas ("Images and graphic
    // credits"). Quando a legenda do Atlas cobre varias fotos, cita o conjunto.
    const FOTOGRAFOS_ATLAS = {
        archaea: "yiftah-s",
        bacteria: "Dr. Sahay, L. Stauffer, UCSF Medical Center, G. Lombard",
        amoebozoa: "Y. Eglit",
        sar: "S. Shimano, Y. Eglit",
        metamonada: "V. Hampl, I. Cepicka",
        ascomycota: "S. Darbey, F. Folini, S. Axford, A. Vizzini",
        basidiomycota: "S. Axford",
        glomeromycota: "S.L. Stürmer, K. Kemmelmeier",
        mucoromycota: "R. Klips",
        zoopagomycota: "G. Barron, H. Krisp, C. Simmons",
        chytridiomycota: "S. Kaynas, mm, S. Porter",
        tardigrada: "D. Robson, D. Loarie",
        rotifera: "R. Moreno, H. Segers, Proyecto Agua",
        nematoda: "H. van Megen, H. Helder, J.G. Baldwin",
        enchytraeidae: "R. Schmelz, A. Murray",
        acari: "K. Makarov",
        collembola: "N. Carrera, J. Méndez, S. Justis, M.J.I. Briones",
        pseudoscorpiones: "A. Murray",
        formicidae: "R.R. Castro Solar",
        isoptera: "M. Bertone, R. Constantino",
        isopoda: "A. Quadros, G. Montesanto, D. Thombs, A. Murray",
        myriapoda: "I.H. Tuf, F. Trnka",
        oligochaeta: "P. Lavelle, S. James, S. Miller, T. Decaëns",
        coleoptera: "Y. Awoki, T. Komatsu, M. Nagano",
        apoidea: "J. Benton",
        araneae: "S. McCann, M. Hedin",
        scorpiones: "M. Hedin, T. Iwane, F. Krohn",
        gastropoda: "B. Lo, S. Jeffery"
    };
    function creditoImagem(id) {
        if (PAGINA_ATLAS[id]) return `${FOTOGRAFOS_ATLAS[id]} — Global Soil Biodiversity Atlas (2016), p. ${PAGINA_ATLAS[id]}`;
        return FONTE_EXTRA[id] ? FONTE_EXTRA[id].texto : "";
    }
    // Versao com links, para o painel (a CC BY-SA pede link da licenca e aviso de alteracao).
    function creditoImagemHtml(id) {
        const f = FONTE_EXTRA[id];
        if (!f) return creditoImagem(id);
        return `<a href="${f.arquivo}" target="_blank" rel="noopener"><em>${f.especie}</em></a>, ${f.autor}, ` +
               `<a href="${LICENCA_CC_BY_SA_3}" target="_blank" rel="noopener">CC BY-SA 3.0</a>, via Wikimedia Commons (${t('acervo.recortada')})`;
    }
    const PAGINA_ATLAS = { archaea: 32, bacteria: 34, amoebozoa: 36, sar: 36, metamonada: 37, ascomycota: 38, basidiomycota: 38, glomeromycota: 40, mucoromycota: 41, zoopagomycota: 41, chytridiomycota: 41, tardigrada: 44, rotifera: 45, nematoda: 46, enchytraeidae: 48, acari: 49, collembola: 50, pseudoscorpiones: 53, formicidae: 54, isoptera: 55, isopoda: 56, myriapoda: 57, oligochaeta: 58, coleoptera: 59, apoidea: 61, araneae: 61, scorpiones: 61, gastropoda: 61 };

    function montarAcervo(dados) {
        dadosAcervo = dados;
        const bancos = dados.bancos || [];

        function montarChip(banco) {
            const el = document.createElement("button");
            el.className = "banco-chip";
            el.type = "button";
            el.dataset.id = banco.id;
            el.dataset.genomas = banco.genomas;
            el.innerHTML = `
                <span class="contagem">${banco.genomas.toLocaleString(localeAtual())}</span>
                <span class="genomas-label">${t("acervo.genomasLabel")}</span>
                <span class="rotulo">${banco.nome}</span>
            `;
            // Fundo opcional: so aplica se a imagem existir (evita circulo quebrado).
            const src = `imagens/grupos/${banco.id}.jpg`;
            if (creditoImagem(banco.id)) el.title = `${banco.nome} · ${t('acervo.foto')}: ${creditoImagem(banco.id)}`;
            const img = new Image();
            // Endereço completo: um url() relativo dentro de variável CSS seria
            // resolvido a partir de css/vitrine.css, não da página.
            img.onload = () => el.style.setProperty("--fundo", `url("${new URL(src, document.baseURI).href}")`);
            img.src = src;
            el.addEventListener("click", () => abrirPainel(banco));
            return el;
        }

        // Duplica a lista pra loop contínuo do carrossel
        [...bancos, ...bancos].forEach(b => track.appendChild(montarChip(b)));
        iniciarCarrossel(track.parentElement, track);

        atualizarTextosAcervo();
    }

    // Carrossel: passa sozinho; para com o mouse em cima ou com um grupo aberto;
    // arrastar (mouse ou dedo) move para frente/tras e, ao soltar, segue com inercia.
    function iniciarCarrossel(wrap, track) {
        const reduzirMovimento = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        const metade = () => track.scrollWidth / 2;          // a lista vem duplicada
        const velocidadeBase = () => metade() / 60;          // uma volta a cada 60 s, como antes
        let deslocamento = 0, ultimoQuadro = null, mouseEmCima = false;
        let pressionado = false, arrastou = false, inicioX = 0, xAnterior = 0, tAnterior = 0;
        let inercia = 0, ignorarClique = false;

        function quadro(t) {
            const dt = ultimoQuadro === null ? 0 : Math.min(0.05, (t - ultimoQuadro) / 1000);
            ultimoQuadro = t;
            if (!arrastou) {
                if (Math.abs(inercia) > 5) {
                    deslocamento += inercia * dt;
                    inercia *= Math.pow(0.05, dt);          // desacelera ate parar
                } else {
                    inercia = 0;
                    const parado = mouseEmCima || wrap.classList.contains("pausado") || reduzirMovimento;
                    if (!parado) deslocamento += velocidadeBase() * dt;
                }
            }
            const m = metade();
            if (m > 0) deslocamento = ((deslocamento % m) + m) % m;
            track.style.transform = `translateX(${-deslocamento}px)`;
            requestAnimationFrame(quadro);
        }
        requestAnimationFrame(quadro);

        wrap.addEventListener("pointerenter", e => { if (e.pointerType === "mouse") mouseEmCima = true; });
        wrap.addEventListener("pointerleave", e => { if (e.pointerType === "mouse") mouseEmCima = false; });

        wrap.addEventListener("pointerdown", e => {
            if (e.button !== 0) return;
            pressionado = true; arrastou = false; inercia = 0;
            inicioX = xAnterior = e.clientX; tAnterior = performance.now();
        });
        wrap.addEventListener("pointermove", e => {
            if (!pressionado) return;
            // So vira arrasto depois de 6 px: um toque/clique simples continua abrindo o grupo.
            if (!arrastou && Math.abs(e.clientX - inicioX) > 6) {
                arrastou = true;
                wrap.classList.add("arrastando");
                wrap.setPointerCapture(e.pointerId);
            }
            if (!arrastou) return;
            const agora = performance.now(), dx = e.clientX - xAnterior;
            deslocamento -= dx;
            const dt = Math.max(0.008, (agora - tAnterior) / 1000);
            inercia = Math.max(-3000, Math.min(3000, 0.7 * inercia + 0.3 * (-dx / dt)));
            xAnterior = e.clientX; tAnterior = agora;
        });
        const soltar = () => {
            if (!pressionado) return;
            pressionado = false;
            if (arrastou) {
                // Soltou parado: sem inercia.
                if (performance.now() - tAnterior > 80) inercia = 0;
                ignorarClique = true;
                setTimeout(() => { ignorarClique = false; }, 60);
            }
            arrastou = false;
            wrap.classList.remove("arrastando");
        };
        wrap.addEventListener("pointerup", soltar);
        wrap.addEventListener("pointercancel", soltar);
        // O clique que termina um arrasto nao abre o grupo.
        wrap.addEventListener("click", e => { if (ignorarClique) { e.stopPropagation(); e.preventDefault(); } }, true);
    }

    function abrirPainel(banco) {
        track.parentElement.classList.add("pausado");
        document.querySelectorAll(".banco-chip").forEach(c => c.classList.toggle("active", c.dataset.id === banco.id));
        bancoAberto = banco;
        painelNome.textContent = banco.nome;
        const credito = creditoImagem(banco.id);
        document.getElementById("painel-credito").innerHTML = credito ? `📷 ${t('acervo.foto')}: ${creditoImagemHtml(banco.id)}` : "";
        painelContagem.textContent = `${banco.genomas.toLocaleString(localeAtual())} ${t('acervo.genomasLabel')}`;
        organismosAtuais = banco.organismos || [];
        buscaEl.value = "";
        renderLista(organismosAtuais);
        painel.classList.add("aberto");
        painel.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    function renderLista(itens) {
        listaEl.innerHTML = "";
        if (itens.length === 0) {
            listaEl.innerHTML = `<div class="sem-resultado">${t("acervo.semOrganismo")}</div>`;
            return;
        }
        itens.forEach(nome => {
            const item = document.createElement("div");
            item.className = "organismo-item";
            item.textContent = `🧬 ${nome}`;
            listaEl.appendChild(item);
        });
    }

    buscaEl.addEventListener("input", () => {
        const q = buscaEl.value.toLowerCase().trim();
        renderLista(organismosAtuais.filter(n => n.toLowerCase().includes(q)));
    });

    // Tabela da vitrine: no PC, clicar e arrastar rola para os lados (no celular o arrasto ja e nativo).
    // Links, botoes, campos e o redimensionador de colunas continuam funcionando normalmente.
    (function tabelaArrastavel() {
        const caixa = document.getElementById("tabela-scroll");
        if (!caixa) return;
        let pressionado = false, arrastou = false, inicioX = 0, rolagemInicial = 0, ignorarClique = false;
        caixa.addEventListener("pointerdown", e => {
            if (e.pointerType !== "mouse" || e.button !== 0) return;
            if (e.target.closest("a, button, input, select, textarea, .col-resizer")) return;
            if (caixa.scrollWidth <= caixa.clientWidth) return;
            pressionado = true; arrastou = false;
            inicioX = e.clientX; rolagemInicial = caixa.scrollLeft;
        });
        caixa.addEventListener("pointermove", e => {
            if (!pressionado) return;
            if (!arrastou && Math.abs(e.clientX - inicioX) > 6) {
                arrastou = true;
                caixa.classList.add("arrastando");
                caixa.setPointerCapture(e.pointerId);
                window.getSelection().removeAllRanges();
            }
            if (arrastou) caixa.scrollLeft = rolagemInicial - (e.clientX - inicioX);
        });
        const soltar = () => {
            if (!pressionado) return;
            pressionado = false;
            if (arrastou) { ignorarClique = true; setTimeout(() => { ignorarClique = false; }, 60); }
            arrastou = false;
            caixa.classList.remove("arrastando");
        };
        caixa.addEventListener("pointerup", soltar);
        caixa.addEventListener("pointercancel", soltar);
        caixa.addEventListener("selectstart", e => { if (arrastou) e.preventDefault(); });
        caixa.addEventListener("click", e => { if (ignorarClique) { e.stopPropagation(); e.preventDefault(); } }, true);
    })();

    document.getElementById("painel-fechar-btn").addEventListener("click", () => {
        painel.classList.remove("aberto");
        track.parentElement.classList.remove("pausado");
        bancoAberto = null;
        document.querySelectorAll(".banco-chip").forEach(c => c.classList.remove("active"));
    });
});
