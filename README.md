# sigtap-dados

Repositório de dados do app **SIGTAP - Procedimentos SUS**. O app consulta o
`manifest.json` daqui e, quando há competência nova, baixa a base direto —
sem precisar de release na App Store nem de revisão da Apple.

## Como publicar (uma vez só)

1. Crie um repositório **público** chamado exatamente `sigtap-dados` em `github.com/isaiasfcabral-stack`
   (o nome importa: a URL está fixa no app; se mudar, ajuste `UPD_MANIFEST` no `index.html`).
2. Suba esta pasta:
   ```bash
   cd "sigtap projeto/sigtap-dados"
   git init && git add -A && git commit -m "primeira publicação (202606)"
   git branch -M main
   git remote add origin git@github.com:isaiasfcabral-stack/sigtap-dados.git
   git push -u origin main
   ```
3. No GitHub: **Settings → Pages → Deploy from a branch → main / (root)**.
4. Teste no navegador: `https://isaiasfcabral-stack.github.io/sigtap-dados/manifest.json`
   (pode levar uns minutos no primeiro deploy).

## Como funciona a atualização mensal

O workflow `atualizar-competencia.yml` roda todo dia ao meio-dia (Brasília):

- olha a página de download do DATASUS;
- se a competência mais nova de lá for maior que a do `manifest.json`, baixa o zip,
  gera `dados/sigtap_data_AAAAMM.json`, o delta contra o mês anterior e atualiza o manifest;
- commita e o GitHub Pages publica. O app avisa os usuários no próximo uso.

Se não houver nada novo, o workflow termina sem mudar nada. Dá para disparar
manualmente em **Actions → Atualizar competência SIGTAP → Run workflow**.

## Se o portal do DATASUS estiver fora do ar ou bloquear o robô

Baixe o zip manualmente no navegador
(<http://sigtap.datasus.gov.br/tabela-unificada/app/download.jsp>) e rode:

```bash
python3 scripts/atualizar.py --zip ~/Downloads/TabelaUnificada_202607_vXXXXXXXXXX.zip
git add -A && git commit -m "Competência 202607" && git push
```

## Garantias de qualidade

- `build_sigtap_data.py` foi validado reproduzindo a base 202606 **100% idêntica**
  ao JSON usado no app a partir do zip oficial.
- O script aborta se vierem menos de 4.000 procedimentos (pacote corrompido/incompleto).
- O app confere o **sha256** do arquivo baixado antes de instalar, e mantém a base
  anterior se qualquer coisa falhar.
- Categorias novas sem rótulo amigável saem no log do workflow — se aparecer alguma,
  adicione o nome bonito em `scripts/rotulos_categorias.json`.

## Estrutura

```
manifest.json                  <- o que o app consulta
dados/sigtap_data_AAAAMM.json  <- uma base por competência (histórico completo)
deltas/delta_ANT_NOVA.json     <- novidades entre competências (tela do app)
scripts/                       <- conversor, delta e orquestrador
```

Dados de referência obtidos da base pública do DATASUS / Ministério da Saúde.
Este repositório não é afiliado ao Ministério da Saúde ou ao DATASUS.
