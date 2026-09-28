# 🔎 Buscar placas em vídeos

Lê as placas de uma **planilha do Google Sheets**, procura cada placa no **nome dos
vídeos** do computador e copia os vídeos encontrados para uma pasta organizada.

Funciona com vídeos em **caminho de rede** (`\\SERVIDOR\Videos`), não só em disco local.
Precisa de Python 3.8+ e usa só a biblioteca padrão — nada para instalar.

```
Google Sheets          →  lê todas as placas
Vídeos do PC           →  procura cada placa no nome dos arquivos
Encontrou?             →  copia o vídeo

📁 RESULTADOS
   ├── ABC1D23
   │   ├── FIAT STRADA-ABC1D23 - STORY.mp4
   │   └── video_02.mp4
   ├── XYZ9A87
   │   └── video_15.mp4
   └── DEF4G56
       └── video_22.mp4
```

---

## 1. Pré-requisito: instalar o Python

O script precisa do **Python 3.8+**. Verifique com:

```powershell
python --version
```

Se der erro ("Python não foi encontrado"), instale pelo PowerShell:

```powershell
winget install Python.Python.3.12
```

Depois **feche e abra o terminal de novo** e teste de novo com `python --version`.

> Nenhuma biblioteca extra é necessária: o script usa só a biblioteca padrão do Python.

---

## 2. Preparar a planilha

1. Crie uma planilha com as placas, uma por linha (coluna A é o padrão):

   | PLACA | OBSERVAÇÃO |
   |-------|------------|
   | ABC-1234 | Fiat Strada |
   | ABC1D23 | Onix |

2. Compartilhe com acesso público de leitura:
   **Compartilhar → "Qualquer pessoa com o link" → Leitor**

3. Copie o link do navegador.

---

## 3. Configurar

Crie o seu `config.py` a partir do exemplo:

```powershell
copy config.exemplo.py config.py
```

> O `config.py` **não** está no repositório de propósito: ele tem o link da sua
> planilha, e quem tem esse link acessa a planilha. Assim ele nunca vaza para o GitHub.

Abra o **`config.py`** e preencha só estas três linhas:

```python
URL_PLANILHA   = "https://docs.google.com/spreadsheets/d/SEU_ID/edit#gid=0"
PASTA_VIDEOS   = r"C:\Users\Administrator\Videos\buscar"
PASTA_RESULTADOS = r"C:\Users\Administrator\Videos\RESULTADOS"
```

O `config.py` é o único arquivo que você precisa editar.

### Vídeos em outro PC (servidor local)

`PASTA_VIDEOS` aceita caminho de rede normalmente, **sem nenhuma alteração no código**:

```python
PASTA_VIDEOS     = r"\\SERVIDOR\Videos\dashcam"   # caminho UNC
PASTA_RESULTADOS = r"D:\RESULTADOS"               # destino em disco local
```

Uma URL `http://` **não** funciona: o script lê o disco, ele não fala HTTP.

Três coisas que importam nesse caso:

**1. Destino em disco local.** A leitura vem pela rede de qualquer jeito, mas gravar também pela rede dobra o custo. Deixe `PASTA_RESULTADOS` em disco local se puder.

**2. Executar com as mesmas credenciais do Explorer.** Se o compartilhamento pede senha, rode o script no mesmo Windows/usuário onde você já acessa. Se precisar reconectar:

```powershell
net use \\SERVIDOR\Videos /user:USUARIO
```

**3. Se a rede ficar lenta**, mapeie uma letra de unidade e aponte para ela:

```powershell
net use Z: \\SERVIDOR\Videos
```

```python
PASTA_VIDEOS = r"Z:\dashcam"
```

Medido nesta máquina com 2.000 vídeos, a varredura de pasta levou **76 ms** em disco local e **497 ms** pela rede. A diferença entre `\\localhost\...` e a unidade mapeada foi pequena (497 ms vs 472 ms), mas esse teste rodou em loopback, sem latência real de rede — em LAN de verdade a unidade mapeada costuma ganhar, porque o Windows resolve o caminho e reaproveita cache entre chamadas.

O `TAMANHO_BUFFER_MB = 4` no `config.py` também ajuda: vídeo grande vem em blocos de 4 MB em vez dos 64 KB–1 MB padrão do Python. Se der erro de memória, baixe para 1.

---

## 4. Testar antes de usar de verdade

Primeiro, confirme que o Python e o script funcionam na máquina:

```powershell
python testar_sem_planilha.py
```

Esse teste **não precisa de internet, nem de planilha, nem dos seus vídeos**: ele
cria uma pasta de vídeo fictícia na pasta temporária do Windows, roda a busca
inteira e confere tudo (se a placa é reconhecida, se a estrutura de pastas sai
certa, se o conteúdo das cópias é idêntico ao original). Não mexe em nada seu.

## 5. Rodar

```powershell
python buscar_placas.py --simular    # testa sem copiar nada (recomendado 1ª vez)
python buscar_placas.py              # faz de verdade
```

Teste rápido sem mexer em planilha nem em pasta:

```powershell
python buscar_placas.py --videos "C:\Users\Eu\Videos" --resultados "C:\Temp\OUT" --planilha placas_exemplo.csv
```

### Opções

| Comando | O que faz |
|---|---|
| `--simular` | Mostra o que seria copiado, sem copiar nada |
| `--debug` | Mostra também os vídeos ignorados |
| `--videos "D:\Videos"` | Sobrescreve a pasta de vídeos |
| `--resultados "D:\OUT"` | Sobrescreve a pasta de destino |
| `--planilha placas.csv` | Lê um CSV local em vez do Google Sheets |
| `--coluna 0` | Força a coluna das placas (padrão: detecção automática) |
| `--tolerante` | Aceita placa colada em outros caracteres no nome |
| `--sobrescrever` | Sobrescreve arquivos que já existem no destino |
| `--debug` | Log detalhado |

---

## 6. Como o matching funciona

O script **não tenta adivinhar** placas em qualquer texto. A planilha é a fonte da
verdade: ele só verifica se alguma placa que está na planilha aparece no nome do arquivo.

| Nome do vídeo | Planilha | Resultado |
|---|---|---|
| `FIAT STRADA-ABC-1234 - STORY.mp4` | `ABC-1234` | ✅ copia |
| `FIAT STRADA ABC1D23.mp4` | `ABC1D23` | ✅ copia |
| `video_ADC1234X_final.mp4` | `ABC1234` | ❌ ignora (placa colada) |
| `Fiat strada abc 1234.mp4` | `ABC1234` | ✅ copia (ignora acentos e caixa) |

Placas dos dois padrões são reconhecidas e comparadas da mesma forma:
- **Antiga:** `ABC1234`, `ABC-1234`
- **Mercosul:** `ABC1D23`

Se o modo normal não encontrar nada, o script **avisa e refaz a busca em modo tolerante**.

### Vários vídeos com a mesma placa

A pasta da placa vai acumulando, sem sobrescrever nada (a menos que use `--sobrescrever`):

```
ABC1D23/
   ├── FIAT STRADA-ABC1D23 - STORY.mp4
   ├── ONIX-ABC1D23-manha.mp4
   └── ABC1D23 (1).mp4
```

Se preferir os nomes `video_01.mp4`, `video_02.mp4`... do seu desenho, troque no `config.py`:

```python
NOMEAR_POR_PADRAO_VIDEO_N = True
```

---

## 7. Relatório

Ao final, o script cria na pasta de resultados:

- **`relatorio.csv`** — planilha com `PLACA | SITUACAO | QTD_VIDEOS | VIDEO(S)`, para filtrar no Excel
- **`relatorio.txt`** — resumo legível com a lista de placas **não encontradas**

Isso responde na hora: *qual placa da planilha não tem vídeo na pasta?*

---

## 8. Solução de problemas

| Mensagem | O que fazer |
|---|---|
| `Python não foi encontrado` | Instale o Python e abra um terminal novo |
| `config.py não encontrado` | Rode `copy config.exemplo.py config.py` (é o normal após clonar) |
| `A planilha recusou o acesso (erro 401/403)` | Compartilhe como "Qualquer pessoa com o link → Leitor" |
| `O Google devolveu uma página HTML` | Mesma coisa: planilha privada |
| `Nenhuma placa foi reconhecida` | Confira se a coluna tem `ABC-1234` e não `1234-ABC`; use `--coluna 0` |
| `Nenhum arquivo de vídeo encontrado` | Confira `PASTA_VIDEOS` e as extensões em `EXTENSOES_VIDEO` |
| `Não consegui acessar o compartilhamento de rede` | O share está fora do ar ou falta credencial. Teste o mesmo caminho no Explorer, ou rode `net use \\SERVIDOR\Videos /user:USUARIO` |
| `A planilha está vazia` | A aba ativa do link (`gid=`) pode estar vazia; copie o link da aba certa |
| Copiou coisa errada | Rode com `--simular` e confira antes; ajustou algo, rode com `--sobrescrever` |

---

## Arquivos

```
buscar_placas.py       ← script principal (CLI)
testar_sem_planilha.py ← teste automático (rode primeiro)
config.exemplo.py      ← modelo de configuração (copie para config.py)
config.py              ← ⚙️  o seu, criado a partir do exemplo (fora do git)
placas.py              ← regras de normalização/comparação de placas
planilha.py            ← leitura do Google Sheets
placas_exemplo.csv     ← planilha de teste local
```
