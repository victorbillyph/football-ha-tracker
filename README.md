# Football Match Tracker

Integração para Home Assistant que rastreia jogos de futebol em tempo real. A cada **30 segundos** a integração consulta a [OpenLigaDB](https://openligadb.de) (API gratuita, sem necessidade de chave) e expõe sensores com placar, status, minuto, fase e adversário para cada time configurado.

## Funcionalidades

- Sem API key — zero cadastro, zero custo
- Rastreio por competição: Mundial, Euro, Copa América, Champions, Premier League, Bundesliga, LaLiga...
- Múltiplos times por competição
- Polling a cada 30 segundos
- Ajuste automático do intervalo enquanto o jogo está ao vivo
- Suporta competições passadas, presentes e futuras

## Sensores criados por time

| Sensor | Descrição | Exemplo |
|---|---|---|
| `sensor.{time}_status` | Status da partida | `Live`, `Not Started`, `Finished` |
| `sensor.{time}_score` | Placar do time | `2` |
| `sensor.{time}_opponent_score` | Placar do adversário | `1` |
| `sensor.{time}_opponent` | Nome do adversário | `Brasil` |
| `sensor.{time}_minute` | Minuto atual | `87` |
| `sensor.{time}_round` | Rodada/fase | `Group Stage`, `Quarter-final` |
| `sensor.{time}_league` | Nome da competição | `World Cup 2026` |

## Instalação

### Via HACS (recomendado)

1. No HACS, vá em *Integrações* → *⋮* → *Repositórios personalizados*
2. Adicione `https://github.com/victorbillyph/football-ha-tracker` como categoria *Integração*
3. Clique em *Explorar e Adicionar Repositórios* → busque por *Football Match Tracker* → instale
4. Reinicie o Home Assistant

### Manual

1. Copie a pasta `custom_components/football/` para dentro do diretório `config/` do seu Home Assistant
2. Reinicie o Home Assistant

## Configuração

1. Vá em **Configurações → Dispositivos e Serviços → Adicionar Integração**
2. Busque por **Football Match Tracker**
3. Escolha entre **Competição popular** ou **Liga personalizada**

### Competições populares disponíveis

| Código | Nome |
|---|---|
| `wm26` | World Cup 2026 |
| `em` | UEFA EURO 2024 |
| `CA2024` | Copa América 2024 |
| `unl2024` | Nations League 2024/25 |
| `bl1` | Bundesliga |
| `epl` | Premier League |
| `laliga1` | LaLiga |
| `cl1` | Champions League |

### Liga personalizada

Se a competição que você quer não está na lista, use o modo *Custom league*.  
Alguns códigos comuns:

- `bl2` — 2. Bundesliga
- `bl3` — 3. Liga
- `CA2021` — Copa América 2021
- `fem08` — UEFA Euro 2008

### Selecionar times

Após escolher a competição, selecione um ou mais times para rastrear.  
Times já configurados aparecem marcados com ✓.

### Adicionar mais times/competições

- Vá em **Configurações → Dispositivos e Serviços → Football Match Tracker → Opções**
- Escolha *Add league/teams* ou *Remove entry*

## Automação de exemplo

```yaml
alias: "Notificar gol do meu time"
trigger:
  - platform: state
    entity_id: sensor.brasil_score
    not_to:
      - unknown
      - none
condition:
  - condition: template
    value_template: "{{ trigger.from_state.state != trigger.to_state.state }}"
action:
  - service: notify.mobile_app
    data:
      title: "GOL! ⚽"
      message: "{{ state_attr('sensor.brasil_score', 'team_name') }} marcou! Placar: {{ states('sensor.brasil_score') }} x {{ states('sensor.brasil_opponent_score') }}"
```

## Dados técnicos

- **Fonte:** [OpenLigaDB](https://openligadb.de) (API REST pública)
- **Polling:** 30 segundos (fixo)
- **Domínio:** `football`
- **Plataformas:** `sensor`
- **Classificação IoT:** Cloud Polling

## Licença

MIT
