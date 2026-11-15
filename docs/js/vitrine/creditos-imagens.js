// Vitrine (docs/index.html) -- créditos das imagens do acervo
// Faz parte da reorganização 2.0; ordem de carregamento em docs/index.html.

// Créditos das fotos dos círculos do acervo (docs/imagens/grupos/<id>.jpg).
// O Atlas permite o uso citando o Atlas e o autor original (p. 2-3); as fotos
// do Wikimedia Commons são CC BY-SA 3.0 (crédito, link da licença e aviso de recorte).

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

// Página do Global Soil Biodiversity Atlas (2016) de onde veio a imagem de cada grupo.
const PAGINA_ATLAS = { archaea: 32, bacteria: 34, amoebozoa: 36, sar: 36, metamonada: 37, ascomycota: 38, basidiomycota: 38, glomeromycota: 40, mucoromycota: 41, zoopagomycota: 41, chytridiomycota: 41, tardigrada: 44, rotifera: 45, nematoda: 46, enchytraeidae: 48, acari: 49, collembola: 50, pseudoscorpiones: 53, formicidae: 54, isoptera: 55, isopoda: 56, myriapoda: 57, oligochaeta: 58, coleoptera: 59, apoidea: 61, araneae: 61, scorpiones: 61, gastropoda: 61 };

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
