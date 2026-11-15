// Vitrine (docs/index.html) -- carrossel e painel do acervo de genomas
// Faz parte da reorganização 2.0; ordem de carregamento em docs/index.html.

// ---- Acervo de Genomas: carrossel de bancos + busca de organismos ----
// Dados vêm de dados/acervo_genomas.json (scripts_auxiliares/
// exportar_acervo_genomas.py), já descontando a curadoria de habitat --
// só o que realmente está no banco de busca aparece aqui.
document.addEventListener("DOMContentLoaded", function() {
    const track = document.getElementById("acervo-carousel-track");
    const statLine = document.getElementById("acervo-stat-line");
    if (!track) return;

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
            mostrarCredito(bancoAberto);
            painelContagem.textContent = `${bancoAberto.genomas.toLocaleString(localeAtual())} ${t('acervo.genomasLabel')}`;
            renderLista(organismosAtuais.filter(n => n.toLowerCase().includes(buscaEl.value.toLowerCase().trim())));
        }
    }
    document.addEventListener("idioma-alterado", atualizarTextosAcervo);

    const painel = document.getElementById("painel-banco");
    const painelNome = document.getElementById("painel-nome");
    const painelContagem = document.getElementById("painel-contagem");
    const listaEl = document.getElementById("lista-organismos");
    const buscaEl = document.getElementById("busca-organismo");
    let organismosAtuais = [];

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
        mostrarCredito(banco);
        painelContagem.textContent = `${banco.genomas.toLocaleString(localeAtual())} ${t('acervo.genomasLabel')}`;
        organismosAtuais = banco.organismos || [];
        buscaEl.value = "";
        renderLista(organismosAtuais);
        painel.classList.add("aberto");
        painel.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    function mostrarCredito(banco) {
        const temCredito = creditoImagem(banco.id) !== "";
        document.getElementById("painel-credito").innerHTML = temCredito ? `📷 ${t('acervo.foto')}: ${creditoImagemHtml(banco.id)}` : "";
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

    document.getElementById("painel-fechar-btn").addEventListener("click", () => {
        painel.classList.remove("aberto");
        track.parentElement.classList.remove("pausado");
        bancoAberto = null;
        document.querySelectorAll(".banco-chip").forEach(c => c.classList.remove("active"));
    });
});
