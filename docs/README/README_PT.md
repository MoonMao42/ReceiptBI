<div align="center">
  
  <img src="../../images/logo.png" width="400" alt="QueryGPT">
  
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

<table>
  <tr>
    <td width="50%">
      <strong>🤖 Processo de Pensamento do Agente Inteligente</strong><br/>
      <img src="../../images/agent-thinking-en.png" width="100%" alt="Interface QueryGPT"/>
      <p align="center">Visualização transparente da cadeia de pensamento</p>
    </td>
    <td width="50%">
      <strong>📊 Visualização de Dados</strong><br/>
      <img src="../../images/data-visualization-en.png" width="100%" alt="Visualização de Dados"/>
      <p align="center">Geração inteligente de gráficos com seleção automática</p>
    </td>
  </tr>
  <tr>
    <td width="50%">
      <strong>👨‍💻 Visão do Desenvolvedor</strong><br/>
      <img src="../../images/developer-view-en.png" width="100%" alt="Visão do Desenvolvedor"/>
      <p align="center">Detalhes completos de execução, SQL e código transparentes</p>
    </td>
    <td width="50%">
      <strong>🌐 Suporte Multilíngue</strong><br/>
      <img src="../../images/main-interface.png" width="100%" alt="Interface Principal"/>
      <p align="center">Suporte para 10 idiomas, acessível globalmente</p>
    </td>
  </tr>
</table>

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

## 🌍 Suporte a Idiomas

O QueryGPT oferece suporte completo para **10 idiomas**, permitindo que usuários de todo o mundo interajam com seus dados em seu idioma nativo:

- 🇨🇳 **Chinês** (Simplificado)
- 🇬🇧 **Inglês**
- 🇷🇺 **Russo**
- 🇪🇸 **Espanhol**
- 🇫🇷 **Francês**
- 🇰🇷 **Coreano**
- 🇩🇪 **Alemão**
- 🇵🇹 **Português**
- 🇯🇵 **Japonês**
- 🇦🇪 **Árabe**

## 🛠️ Stack Tecnológico

### Backend
- **Python 3.10.x** - Linguagem principal (obrigatório para OpenInterpreter 0.4.3)
- **Flask** - Framework web
- **OpenInterpreter 0.4.3** - Motor de execução de código inteligente
- **PyMySQL** - Conector de banco de dados MySQL
- **Pandas** - Processamento e análise de dados
- **Plotly** - Visualização interativa de dados
- **NumPy** - Computação numérica

### Frontend
- **HTML5/CSS3** - Interface moderna e responsiva
- **JavaScript (ES6+)** - Lógica de aplicação
- **Bootstrap** - Framework de UI
- **Chart.js/Plotly.js** - Bibliotecas de visualização

### Banco de Dados
- **MySQL** ou bancos de dados compatíveis
- **Doris DB** - Suporte para análise OLAP
- Suporte para múltiplos bancos de dados simultaneamente

## 🚀 Início Rápido

### Instalação Inicial

```bash
# 1. Clone o projeto
git clone https://github.com/MoonMao42/ReceiptBI.git
cd QueryGPT

# 2. Execute o script de configuração (configura automaticamente o ambiente)
./setup.sh

# 3. Inicie o serviço
./start.sh
```

### Uso Subsequente

```bash
# Início rápido direto
./quick_start.sh
```

O serviço será executado em http://localhost:5000 por padrão

> **Nota**: Se a porta 5000 estiver ocupada (por exemplo, AirPlay no macOS), o sistema selecionará automaticamente a próxima porta disponível (5001-5010) e exibirá a porta real usada na inicialização.

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

A camada semântica melhora a compreensão de termos de negócios, ajudando o sistema a entender melhor sua linguagem de negócios.

1. **Copie o arquivo de exemplo**
   ```bash
   cp backend/semantic_layer.json.example backend/semantic_layer.json
   ```

2. **Modifique a configuração com base em suas necessidades de negócios**

## 💡 Como Usar

### Exemplos de Consultas

O QueryGPT entende consultas em linguagem natural. Aqui estão alguns exemplos:

#### Consultas Básicas
- "Mostre todos os produtos"
- "Quantos clientes temos?"
- "Liste as vendas de hoje"

#### Análise de Dados
- "Mostre a tendência de vendas dos últimos 6 meses"
- "Compare as vendas deste ano com o ano passado"
- "Quais são os 10 produtos mais vendidos?"
- "Analise a distribuição de vendas por região"

#### Visualizações
- "Crie um gráfico de pizza das vendas por categoria"
- "Gere um gráfico de linha do crescimento de usuários"
- "Visualize a distribuição de receita mensal"

#### Análise Complexa
- "Calcule a taxa de retenção de clientes"
- "Identifique padrões sazonais nas vendas"
- "Preveja as vendas do próximo trimestre"
- "Encontre correlações entre preço e volume de vendas"

### Modos de Visualização

1. **Modo Usuário**: Interface simplificada focada em resultados e visualizações
2. **Modo Desenvolvedor**: Visão completa com SQL gerado, código Python e logs de execução

### Dicas de Uso

- Use linguagem natural - o sistema converte automaticamente para SQL
- Seja específico sobre o período de tempo desejado
- Mencione "gráfico" ou "visualização" para gerar gráficos automáticos
- O sistema mantém contexto de conversas anteriores
- Você pode fazer perguntas de acompanhamento baseadas em resultados anteriores

## 📋 Requisitos do Sistema

### Hardware Mínimo
- **CPU**: 2 cores
- **RAM**: 4 GB
- **Armazenamento**: 10 GB de espaço livre

### Hardware Recomendado
- **CPU**: 4+ cores
- **RAM**: 8 GB ou mais
- **Armazenamento**: 20 GB de espaço livre
- **Rede**: Conexão estável para APIs de IA

### Software
- **Sistema Operacional**: Linux, macOS, Windows (com WSL)
- **Python**: 3.10.x (obrigatório, versão específica para OpenInterpreter)
- **Node.js**: 14+ (para desenvolvimento frontend)
- **MySQL**: 5.7+ ou MariaDB 10.3+

### Requisitos de API
- Chave de API OpenAI (ou endpoint compatível)
- Opcional: API keys para outros modelos (Claude, Gemini, etc.)

## 🔒 Segurança

### Proteção de Dados
- Permissões somente leitura no banco de dados
- Proteção contra injeção SQL com validação regex
- Mascaramento automático de dados sensíveis
- Credenciais armazenadas em variáveis de ambiente

### Práticas de Segurança
- Nunca commitar arquivos .env
- Usar HTTPS em produção
- Limitar origens CORS
- Implementar rate limiting para APIs

## 📊 Comparação com Outras Soluções

| Característica | **QueryGPT** | Vanna AI | DB-GPT | TableGPT | Text2SQL.AI |
|----------------|:------------:|:--------:|:------:|:--------:|:-----------:|
| **Custo** | **✅ Gratuito** | ⭕ Versão paga | ✅ Gratuito | ❌ Pago | ❌ Pago |
| **Código Aberto** | **✅** | ✅ | ✅ | ❌ | ❌ |
| **Implementação Local** | **✅** | ✅ | ✅ | ❌ | ❌ |
| **Executa Código Python** | **✅ Ambiente completo** | ❌ | ❌ | ❌ | ❌ |
| **Visualização** | **✅ Programável** | ⭕ Gráficos predefinidos | ✅ Gráficos ricos | ✅ Gráficos ricos | ⭕ Básico |
| **Multi-idioma** | **✅ 10 idiomas** | ⭕ Limitado | ⭕ Limitado | ⭕ Limitado | ⭕ Limitado |
| **Exploração Autônoma** | **✅** | ❌ | ⭕ Básico | ⭕ Básico | ❌ |
| **Pensamento em Tempo Real** | **✅** | ❌ | ❌ | ❌ | ❌ |
| **Extensibilidade** | **✅ Ilimitada** | ❌ | ❌ | ❌ | ❌ |

## 🤝 Contribuindo

Contribuições são bem-vindas! Por favor, sinta-se à vontade para submeter Pull Requests.

1. Fork o projeto
2. Crie sua branch de feature (`git checkout -b feature/RecursoIncrivel`)
3. Commit suas mudanças (`git commit -m 'Adicionar RecursoIncrivel'`)
4. Push para a branch (`git push origin feature/RecursoIncrivel`)
5. Abra um Pull Request

## 📄 Licença

Este projeto está licenciado sob a Licença MIT - veja o arquivo [LICENSE](LICENSE) para detalhes.

## 🙏 Agradecimentos

- [OpenInterpreter](https://github.com/OpenInterpreter/open-interpreter) - Motor de execução de código inteligente
- [Flask](https://flask.palletsprojects.com/) - Framework web
- [Plotly](https://plotly.com/) - Biblioteca de visualização
- Todos os contribuidores que ajudaram a tornar este projeto melhor

## 📞 Contato e Suporte

- **Issues**: [GitHub Issues](https://github.com/MoonMao42/ReceiptBI/issues)
- **Discussões**: [GitHub Discussions](https://github.com/MoonMao42/ReceiptBI/discussions)
- **Autor**: MoonMao42

---

<div align="center">
  <p>Feito com ❤️ para a comunidade de análise de dados</p>
  <p>⭐ Se este projeto te ajudou, considere dar uma estrela! ⭐</p>
</div>