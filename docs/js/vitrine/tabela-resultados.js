// Vitrine (docs/index.html) -- tabela de análises
// Faz parte da reorganização 2.0; ordem de carregamento em docs/index.html.

// ---- Tabela de análises: ordenação, filtros, paginação, largura das colunas ----
// As linhas (<tr>) já vêm no HTML: main.py/main_issues.py inserem cada análise
// nova antes do marcador <!-- NOVAS_LINHAS --> de docs/index.html.
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

    // Contagem de resultados e texto da paginação dependem do idioma.
    document.addEventListener("idioma-alterado", aplicarFiltro);

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
});
