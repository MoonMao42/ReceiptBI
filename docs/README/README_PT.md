<div align="center">
  
  <img src="../images/logo.png" width="400" alt="QueryGPT">
  
  <br/>
  
  <p>
    <a href="README.md">English</a> •
    <a href="docs/README_CN.md">简体中文</a> •
    <a href="#">Português</a>
  </p>
  
  <br/>
  
  [![License](https://img.shields.io/badge/Licença-MIT-yellow.svg?style=for-the-badge)](LICENSE)
  [![Python](https://img.shields.io/badge/Python-3.10+-blue.svg?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
  [![OpenInterpreter](https://img.shields.io/badge/OpenInterpreter-0.4.3-green.svg?style=for-the-badge)](https://github.com/OpenInterpreter/open-interpreter)
  [![Stars](https://img.shields.io/github/stars/MoonMao42/ReceiptBI?style=for-the-badge&color=yellow)](https://github.com/MoonMao42/ReceiptBI/stargazers)
  
  <br/>
  
  <h3>Um Agente Inteligente de Análise de Dados baseado em OpenInterpreter</h3>
  <p><i>Converse com seu banco de dados em linguagem natural</i></p>
  
</div>

<br/>

---

## ✨ Principais Vantagens

**Pensa Como um Analista de Dados**
- **Exploração Autônoma**: Examina proativamente estruturas de tabelas e dados de amostra ao encontrar problemas
- **Validação Multi-rodadas**: Verifica novamente quando anomalias são encontradas para garantir resultados precisos
- **Análise Complexa**: Não apenas SQL, pode executar Python para análise estatística e aprendizado de máquina
- **Pensamento Visível**: Exibição em tempo real do processo de raciocínio do Agente (Chain-of-Thought)

## 📸 Capturas de Tela do Sistema

<img src="../images/agent-thinking-en.png" width="100%" alt="Interface QueryGPT"/>

**Exibição em tempo real do processo de pensamento da IA, análise complexa de dados através de conversas em português.**

---

<img src="../images/data-visualization-en.png" width="100%" alt="Visualização de Dados"/>

**Geração automática de gráficos interativos, insights de dados em um relance.**

---

<img src="../images/developer-view-en.png" width="100%" alt="Visão do Desenvolvedor"/>

**Execução de código totalmente transparente, suportando SQL e Python como motores duplos.**

## 🌟 Recursos Principais

### Capacidades Centrais do Agente
- **Exploração Autônoma de Dados**: O Agente compreende proativamente a estrutura de dados e explora relacionamentos
- **Raciocínio Multi-rodadas**: Como um analista, investiga profundamente quando surgem problemas
- **Chain-of-Thought**: Exibição em tempo real do processo de pensamento do Agente, intervenção possível a qualquer momento
- **Memória de Contexto**: Compreende o histórico de conversas, suporta análise contínua multi-rodadas

### Capacidades de Análise de Dados
- **SQL + Python**: Não limitado ao SQL, pode executar processamento complexo de dados em Python
- **Análise Estatística**: Análise automática de correlação, previsão de tendências, detecção de anomalias
- **Termos de Negócios**: Compreensão nativa de conceitos como YoY (ano a ano), MoM (mês a mês), retenção, recompra
- **Visualização Inteligente**: Seleciona automaticamente o melhor tipo de gráfico baseado nas características dos dados

### Recursos do Sistema
- **Suporte Multi-modelo**: Alterne livremente entre GPT-4, Claude, Gemini, modelos locais Ollama
- **Implementação Flexível**: Suporta API em nuvem ou implementação local Ollama, dados nunca saem das instalações
- **Registros de Histórico**: Salva processo de análise, suporta rastreamento e compartilhamento
- **Segurança de Dados**: Permissões somente leitura, proteção contra injeção SQL, mascaramento de dados sensíveis
- **Exportação Flexível**: Suporta formatos Excel, PDF, HTML e outros

## 📦 Requisitos Técnicos

- Python 3.10.x (obrigatório, dependência do OpenInterpreter 0.4.3)
- MySQL ou banco de dados compatível

> Windows: Execute no WSL (não execute scripts no PowerShell/CMD).

## 📊 Comparação de Produtos

| Dimensão de Comparação | **QueryGPT** | Vanna AI | DB-GPT | TableGPT | Text2SQL.AI |
|----------------------|:------------:|:--------:|:------:|:--------:|:-----------:|
| **Custo** | **✅ Gratuito** | ⭕ Versão paga | ✅ Gratuito | ❌ Pago | ❌ Pago |
| **Código Aberto** | **✅** | ✅ | ✅ | ❌ | ❌ |
| **Implementação Local** | **✅** | ✅ | ✅ | ❌ | ❌ |
| **Executa Código Python** | **✅ Ambiente completo** | ❌ | ❌ | ❌ | ❌ |
| **Capacidade de Visualização** | **✅ Programável** | ⭕ Gráficos predefinidos | ✅ Gráficos ricos | ✅ Gráficos ricos | ⭕ Básico |
| **Compreensão de Termos de Negócios** | **✅ Nativo** | ⭕ Básico | ✅ Bom | ✅ Excelente | ⭕ Básico |
| **Exploração Autônoma do Agente** | **✅** | ❌ | ⭕ Básico | ⭕ Básico | ❌ |
| **Exibição de Pensamento em Tempo Real** | **✅** | ❌ | ❌ | ❌ | ❌ |
| **Capacidade de Extensão** | **✅ Extensão ilimitada** | ❌ | ❌ | ❌ | ❌ |

### Nossas Diferenças Principais
- **Ambiente Python Completo**: Não são recursos predefinidos, mas um ambiente de execução Python real onde você pode escrever qualquer código
- **Extensibilidade Ilimitada**: Precisa de novos recursos? Basta instalar novas bibliotecas, sem esperar atualizações do produto
- **Exploração Autônoma do Agente**: Investiga proativamente quando encontra problemas, não é apenas uma consulta única simples
- **Processo de Pensamento Transparente**: Veja o que a IA está pensando em tempo real, pode intervir e orientar a qualquer momento
- **Verdadeiramente Gratuito e Open Source**: Licença MIT, sem barreiras de pagamento

## 🚀 Início Rápido

### Primeiro Uso

```bash
# 1. Clone o projeto
git clone https://github.com/MoonMao42/ReceiptBI.git
cd QueryGPT

# 2. Execute o script de configuração (configura automaticamente o ambiente)
./setup.sh

# 3. Inicie o serviço
./start.sh
```

### Uso Posterior

```bash
# Início rápido direto
./start.sh
```

O serviço será executado em http://localhost:5000 por padrão

> **Nota**: Se a porta 5000 estiver ocupada (por exemplo, AirPlay no macOS), o sistema selecionará automaticamente a próxima porta disponível (5001-5010) e exibirá a porta real usada na inicialização.

> Windows: Execute no WSL (não execute scripts pelo PowerShell/CMD).

## ⚙️ Configuração

### Configuração Básica

1. **Copie o arquivo de configuração de ambiente**
   ```bash
   cp .env.example .env
   ```

2. **Edite o arquivo .env para configurar o seguinte**
   - `OPENAI_API_KEY`: Sua chave de API OpenAI
   - `OPENAI_BASE_URL`: Endpoint da API (opcional, padrão para endpoint oficial)
   - Informações de conexão do banco de dados

### Configuração da Camada Semântica (Opcional)

A camada semântica melhora a compreensão de termos de negócios, ajudando o sistema a entender melhor sua linguagem de negócios. **Esta é uma configuração opcional, não configurá-la não afeta as funcionalidades básicas.**

1. **Copie o arquivo de exemplo**
   ```bash
   cp backend/semantic_layer.json.example backend/semantic_layer.json
   ```

2. **Modifique a configuração com base em suas necessidades de negócios**
   
   A configuração da camada semântica contém três partes:
   - **Mapeamento de Banco de Dados**: Define o significado comercial do banco de dados
   - **Tabelas de Negócios Principais**: Mapeia tabelas e campos de negócios importantes
   - **Índice de Busca Rápida**: Pesquisa rápida de termos comuns

3. **Exemplo de Configuração**
   ```json
   {
     "Tabelas de Negócios Principais": {
       "Gestão de Pedidos": {
         "Caminho da Tabela": "database.orders",
         "Palavras-chave": ["pedido", "venda", "transação"],
         "Campos Obrigatórios": {
           "order_id": "Número do Pedido",
           "amount": "Valor"
         }
       }
     }
   }
   ```

> **Nota**: 
> - O arquivo da camada semântica contém informações comerciais sensíveis e foi adicionado ao `.gitignore`, não será enviado ao controle de versão
> - Quando a camada semântica não está configurada, o sistema usa a configuração padrão e ainda pode realizar consultas de dados normalmente
> - Para instruções detalhadas de configuração, consulte [backend/SEMANTIC_LAYER_SETUP.md](backend/SEMANTIC_LAYER_SETUP.md)

## 📁 Estrutura do Projeto

```
QueryGPT/
├── backend/              # Serviço backend
│   ├── app.py           # Entrada principal da aplicação Flask
│   ├── database.py      # Gerenciamento de conexão de banco de dados
│   ├── interpreter_manager.py  # Interpretador de consultas
│   ├── history_manager.py      # Gerenciamento de histórico
│   └── config_loader.py        # Carregador de configuração
├── frontend/            # Interface frontend
│   ├── templates/       # Modelos HTML
│   └── static/          # Recursos estáticos
│       ├── css/         # Arquivos de estilo
│       └── js/          # JavaScript
├── docs/                # Documentação do projeto
├── logs/                # Diretório de logs
├── output/              # Arquivos de saída
├── requirements.txt     # Dependências Python
└── .env.example         # Exemplo de configuração
```

## 🔌 API

### Interface de Consulta

```http
POST /api/chat
Content-Type: application/json

{
  "message": "Consultar total de vendas deste mês",
  "model": "default"
}
```

### Histórico

```http
GET /api/history/conversations    # Obter lista de histórico
GET /api/history/conversation/:id # Obter detalhes
DELETE /api/history/conversation/:id # Excluir registro
```

### Verificação de Saúde

```http
GET /api/health
```

## 🔒 Informações de Segurança

- Suporta apenas consultas somente leitura (SELECT, SHOW, DESCRIBE)
- Filtra automaticamente declarações SQL perigosas
- Usuários do banco de dados devem ser configurados com permissões somente leitura

## 📄 Licença

MIT License - Veja o arquivo [LICENSE](LICENSE) para detalhes

## 🆕 Atualizações Recentes

- 2025-09-05 – Otimização de velocidade de inicialização: Removido teste automático em lote ao entrar na página de modelos pela primeira vez, reduzindo requisições desnecessárias e evitando escrita incorreta de estado.

## 👨‍💻 Autor

- **Autor**: MoonMao42
- **GitHub**: [@MoonMao42](https://github.com/MoonMao42)
- **Data de Criação**: Agosto de 2025

## ⭐ Star History

<div align="center">
  <a href="https://star-history.com/#MoonMao42/ReceiptBI&Date">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=MoonMao42/ReceiptBI&type=Date&theme=dark" />
      <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=MoonMao42/ReceiptBI&type=Date" />
      <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=MoonMao42/ReceiptBI&type=Date" />
    </picture>
  </a>
</div>

## 🤝 Contribuição

Bem-vindo para enviar Issues e Pull Requests.

1. Fork este projeto
2. Crie uma branch de recurso (`git checkout -b feature/AmazingFeature`)
3. Commit suas alterações (`git commit -m 'Add some AmazingFeature'`)
4. Push para a branch (`git push origin feature/AmazingFeature`)
5. Abra um Pull Request
