"""
Dashboard Web para o Bot de Torneios

Opções de Dashboard:
1. FastAPI + Jinja2 (Recomendado) - Simples, rápido, moderno
2. Flask + Bootstrap - Tradicional, fácil
3. Next.js + FastAPI (Avançado) - SPA completo

Vamos usar FastAPI + Jinja2 por ser mais moderno e assíncrono
"""

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timedelta
from typing import Optional
import httpx

from config import DashboardConfig, BotConfig
from database.models import Event, Team, Match, User, Inscription, Payment
from database.manager import get_db_session

# =============================================
# INICIALIZAÇÃO DO FASTAPI
# =============================================

app = FastAPI(
    title="Tournament Bot Dashboard",
    description="Dashboard para gerenciamento de torneios",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=DashboardConfig.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Templates e arquivos estáticos
templates = Jinja2Templates(directory="dashboard/templates")
app.mount("/static", StaticFiles(directory="dashboard/static"), name="static")

# =============================================
# AUTENTICAÇÃO DISCORD OAUTH2
# =============================================

class DiscordOAuth:
    """Sistema de autenticação com Discord OAuth2"""
    
    OAUTH_URL = "https://discord.com/api/oauth2/authorize"
    TOKEN_URL = "https://discord.com/api/oauth2/token"
    API_URL = "https://discord.com/api/v10"
    
    @staticmethod
    def get_oauth_url() -> str:
        """Retorna URL para autorização OAuth"""
        params = {
            "client_id": DashboardConfig.DISCORD_CLIENT_ID,
            "redirect_uri": DashboardConfig.DISCORD_REDIRECT_URI,
            "response_type": "code",
            "scope": "identify guilds"
        }
        query = "&".join([f"{k}={v}" for k, v in params.items()])
        return f"{DiscordOAuth.OAUTH_URL}?{query}"
    
    @staticmethod
    async def exchange_code(code: str) -> dict:
        """Troca o código por access token"""
        data = {
            "client_id": DashboardConfig.DISCORD_CLIENT_ID,
            "client_secret": DashboardConfig.DISCORD_CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": DashboardConfig.DISCORD_REDIRECT_URI
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(DiscordOAuth.TOKEN_URL, data=data)
            return response.json()
    
    @staticmethod
    async def get_user_info(access_token: str) -> dict:
        """Obtém informações do usuário"""
        headers = {"Authorization": f"Bearer {access_token}"}
        
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{DiscordOAuth.API_URL}/users/@me", headers=headers)
            return response.json()

# =============================================
# ROTAS DE AUTENTICAÇÃO
# =============================================

@app.get("/login")
async def login():
    """Redireciona para OAuth do Discord"""
    return {"url": DiscordOAuth.get_oauth_url()}

@app.get("/callback")
async def oauth_callback(code: str):
    """Callback do OAuth"""
    try:
        token_data = await DiscordOAuth.exchange_code(code)
        user_info = await DiscordOAuth.get_user_info(token_data['access_token'])
        
        # Salvar sessão (implementar com JWT ou sessions)
        return {"user": user_info, "token": token_data['access_token']}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# =============================================
# ROTAS DO DASHBOARD
# =============================================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Página inicial do dashboard"""
    return templates.TemplateResponse("home.html", {
        "request": request,
        "title": "Tournament Bot Dashboard"
    })

@app.get("/events", response_class=HTMLResponse)
async def events_page(request: Request, db: AsyncSession = Depends(get_db_session)):
    """Página de eventos"""
    # Buscar eventos
    result = await db.execute(select(Event).order_by(Event.created_at.desc()))
    events = result.scalars().all()
    
    return templates.TemplateResponse("events.html", {
        "request": request,
        "events": events,
        "title": "Eventos"
    })

@app.get("/event/{event_id}", response_class=HTMLResponse)
async def event_detail(
    request: Request,
    event_id: int,
    db: AsyncSession = Depends(get_db_session)
):
    """Detalhes de um evento específico"""
    event = await db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Evento não encontrado")
    
    # Buscar times do evento
    teams_result = await db.execute(
        select(Team).where(Team.event_id == event_id)
    )
    teams = teams_result.scalars().all()
    
    # Buscar confrontos
    matches_result = await db.execute(
        select(Match).where(Match.event_id == event_id)
    )
    matches = matches_result.scalars().all()
    
    return templates.TemplateResponse("event_detail.html", {
        "request": request,
        "event": event,
        "teams": teams,
        "matches": matches,
        "title": event.name
    })

# =============================================
# API ENDPOINTS (JSON)
# =============================================

@app.get("/api/stats/overview")
async def stats_overview(db: AsyncSession = Depends(get_db_session)):
    """Estatísticas gerais"""
    
    # Total de eventos
    events_count = await db.scalar(select(func.count(Event.id)))
    
    # Total de times
    teams_count = await db.scalar(select(func.count(Team.id)))
    
    # Total de partidas
    matches_count = await db.scalar(select(func.count(Match.id)))
    
    # Eventos ativos
    active_events = await db.scalar(
        select(func.count(Event.id)).where(Event.status == 'in_progress')
    )
    
    return {
        "total_events": events_count,
        "total_teams": teams_count,
        "total_matches": matches_count,
        "active_events": active_events
    }

@app.get("/api/events")
async def get_events(
    status: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db_session)
):
    """Lista eventos com filtros"""
    query = select(Event).order_by(Event.created_at.desc()).limit(limit)
    
    if status:
        query = query.where(Event.status == status)
    
    result = await db.execute(query)
    events = result.scalars().all()
    
    return [{
        "id": e.id,
        "name": e.name,
        "status": e.status.value,
        "teams_count": len(e.teams),
        "created_at": e.created_at.isoformat()
    } for e in events]

@app.get("/api/event/{event_id}/bracket")
async def get_bracket(event_id: int, db: AsyncSession = Depends(get_db_session)):
    """Retorna chaveamento do evento"""
    event = await db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Evento não encontrado")
    
    # Buscar todas as partidas
    matches_result = await db.execute(
        select(Match).where(Match.event_id == event_id).order_by(Match.phase, Match.match_number)
    )
    matches = matches_result.scalars().all()
    
    # Organizar por fase
    bracket = {}
    for match in matches:
        phase = match.phase.value
        if phase not in bracket:
            bracket[phase] = []
        
        bracket[phase].append({
            "match_number": match.match_number,
            "team1": match.team1.name if match.team1 else "TBD",
            "team2": match.team2.name if match.team2 else "TBD",
            "winner": match.winner.name if match.winner else None,
            "score": f"{match.team1_score} - {match.team2_score}"
        })
    
    return bracket

@app.get("/api/event/{event_id}/standings")
async def get_standings(event_id: int, db: AsyncSession = Depends(get_db_session)):
    """Classificação dos times"""
    teams_result = await db.execute(
        select(Team)
        .where(Team.event_id == event_id)
        .order_by(Team.points.desc(), Team.wins.desc(), Team.kills.desc())
    )
    teams = teams_result.scalars().all()
    
    return [{
        "position": idx + 1,
        "name": team.name,
        "points": team.points,
        "wins": team.wins,
        "losses": team.losses,
        "kills": team.kills
    } for idx, team in enumerate(teams)]

@app.get("/api/inscriptions/pending")
async def pending_inscriptions(db: AsyncSession = Depends(get_db_session)):
    """Inscrições pendentes de aprovação"""
    result = await db.execute(
        select(Inscription)
        .where(Inscription.approved == False)
        .order_by(Inscription.created_at.desc())
    )
    inscriptions = result.scalars().all()
    
    return [{
        "id": i.id,
        "team_name": i.team_name,
        "contact": i.contact,
        "paid": i.paid,
        "created_at": i.created_at.isoformat()
    } for i in inscriptions]

@app.post("/api/inscription/{inscription_id}/approve")
async def approve_inscription(
    inscription_id: int,
    db: AsyncSession = Depends(get_db_session)
):
    """Aprova uma inscrição"""
    inscription = await db.get(Inscription, inscription_id)
    if not inscription:
        raise HTTPException(status_code=404, detail="Inscrição não encontrada")
    
    inscription.approved = True
    await db.commit()
    
    return {"message": "Inscrição aprovada com sucesso"}

@app.get("/api/payments/recent")
async def recent_payments(
    limit: int = 20,
    db: AsyncSession = Depends(get_db_session)
):
    """Pagamentos recentes"""
    result = await db.execute(
        select(Payment)
        .order_by(Payment.created_at.desc())
        .limit(limit)
    )
    payments = result.scalars().all()
    
    return [{
        "id": p.id,
        "amount": p.amount,
        "status": p.status.value,
        "created_at": p.created_at.isoformat(),
        "paid_at": p.paid_at.isoformat() if p.paid_at else None
    } for p in payments]

# =============================================
# WEBHOOK PARA CONFIRMAÇÃO DE PAGAMENTO
# =============================================

@app.post("/webhook/payment")
async def payment_webhook(request: Request, db: AsyncSession = Depends(get_db_session)):
    """
    Webhook para receber confirmações de pagamento
    Este endpoint será chamado pelo Mercado Pago ou OpenPix
    """
    
    # Verificar assinatura
    signature = request.headers.get('x-signature') or request.headers.get('x-webhook-signature')
    body = await request.body()
    
    # TODO: Implementar verificação de assinatura específica do provider
    
    data = await request.json()
    
    # OpenPix webhook format
    if 'charge' in data:
        charge = data['charge']
        correlation_id = charge['correlationID']
        status = charge['status']
        
        if status == 'COMPLETED':
            # Buscar pagamento pelo correlation_id
            inscription_id = int(correlation_id.split('_')[1])
            
            payment_result = await db.execute(
                select(Payment).where(Payment.inscription_id == inscription_id)
            )
            payment = payment_result.scalar_one_or_none()
            
            if payment:
                payment.status = PaymentStatus.APPROVED
                payment.paid_at = datetime.now()
                payment.transaction_id = charge.get('transactionID')
                
                # Aprovar inscrição
                inscription = await db.get(Inscription, inscription_id)
                inscription.paid = True
                inscription.approved = True
                
                await db.commit()
                
                # Enviar notificação no Discord (implementar)
                
    # Mercado Pago webhook format
    elif 'data' in data and 'id' in data['data']:
        payment_id = data['data']['id']
        # Buscar status do pagamento na API do Mercado Pago
        # Atualizar banco de dados
    
    return {"status": "ok"}

# =============================================
# EXECUÇÃO DO SERVIDOR
# =============================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.dashboard:app",
        host=DashboardConfig.HOST,
        port=DashboardConfig.PORT,
        reload=True
    )

"""
# =============================================
# TEMPLATES HTML BÁSICOS
# =============================================

Criar pasta: dashboard/templates/

## base.html
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }} - Tournament Bot</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="/static/css/style.css">
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <div class="container">
            <a class="navbar-brand" href="/">🏆 Tournament Bot</a>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navbarNav">
                <ul class="navbar-nav ms-auto">
                    <li class="nav-item"><a class="nav-link" href="/">Home</a></li>
                    <li class="nav-item"><a class="nav-link" href="/events">Eventos</a></li>
                    <li class="nav-item"><a class="nav-link" href="/stats">Estatísticas</a></li>
                    <li class="nav-item"><a class="nav-link" href="/login">Login</a></li>
                </ul>
            </div>
        </div>
    </nav>
    
    <main class="container mt-4">
        {% block content %}{% endblock %}
    </main>
    
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script src="/static/js/main.js"></script>
</body>
</html>

## home.html
{% extends "base.html" %}

{% block content %}
<div class="row">
    <div class="col-md-3">
        <div class="card text-center">
            <div class="card-body">
                <h5 class="card-title">Eventos Ativos</h5>
                <h2 id="active-events">-</h2>
            </div>
        </div>
    </div>
    <div class="col-md-3">
        <div class="card text-center">
            <div class="card-body">
                <h5 class="card-title">Total de Times</h5>
                <h2 id="total-teams">-</h2>
            </div>
        </div>
    </div>
    <div class="col-md-3">
        <div class="card text-center">
            <div class="card-body">
                <h5 class="card-title">Partidas</h5>
                <h2 id="total-matches">-</h2>
            </div>
        </div>
    </div>
    <div class="col-md-3">
        <div class="card text-center">
            <div class="card-body">
                <h5 class="card-title">Eventos Totais</h5>
                <h2 id="total-events">-</h2>
            </div>
        </div>
    </div>
</div>

<script>
fetch('/api/stats/overview')
    .then(r => r.json())
    .then(data => {
        document.getElementById('active-events').textContent = data.active_events;
        document.getElementById('total-teams').textContent = data.total_teams;
        document.getElementById('total-matches').textContent = data.total_matches;
        document.getElementById('total-events').textContent = data.total_events;
    });
</script>
{% endblock %}

# =============================================
# ALTERNATIVAS DE DASHBOARD
# =============================================

1. **Grafana + Prometheus** (Avançado)
   - Para métricas e monitoramento em tempo real
   - Gráficos profissionais
   - Requer mais setup

2. **Streamlit** (Python Puro)
   - Dashboard interativo 100% Python
   - Muito rápido para prototipar
   - Menos customizável visualmente

3. **Retool** (No-Code)
   - Ferramenta drag-and-drop
   - Conecta direto no DB
   - Pago (mas tem free tier)

4. **Next.js + Chart.js** (Moderno)
   - SPA completa
   - Muito responsivo
   - Requer conhecimento de React

RECOMENDAÇÃO: Comece com FastAPI + Jinja2 (o código acima)
"""
