import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta
from typing import Optional
import asyncio

from config import BotConfig, PaymentConfig, Messages
from api.pix import PaymentManager
from database.models import Inscription, Payment, PaymentStatus, Event, Team
from utils.embeds import create_inscription_embed, create_payment_embed

class InscriptionModal(discord.ui.Modal, title="Inscrição no Torneio"):
    """Modal para coletar informações da inscrição"""
    
    team_name = discord.ui.TextInput(
        label="Nome do Time",
        placeholder="Ex: Los Grandes",
        required=True,
        max_length=50
    )
    
    members = discord.ui.TextInput(
        label="Membros (5 jogadores)",
        placeholder="Player1, Player2, Player3, Player4, Player5",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=500
    )
    
    contact = discord.ui.TextInput(
        label="Contato (WhatsApp ou Discord)",
        placeholder="(61) 98765-4321 ou @usuario#1234",
        required=True,
        max_length=100
    )
    
    def __init__(self, event_id: int, db_session, payment_manager: PaymentManager):
        super().__init__()
        self.event_id = event_id
        self.db = db_session
        self.payment_manager = payment_manager
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        # Validar membros
        members_list = [m.strip() for m in self.members.value.split(',')]
        if len(members_list) < 3:
            await interaction.followup.send(
                Messages.error("O time precisa ter pelo menos 3 membros!"),
                ephemeral=True
            )
            return
        
        # Criar inscrição no banco
        inscription = Inscription(
            event_id=self.event_id,
            user_id=str(interaction.user.id),
            team_name=self.team_name.value,
            members_info=members_list,
            contact=self.contact.value,
            approved=False,
            paid=False
        )
        
        self.db.add(inscription)
        await self.db.commit()
        await self.db.refresh(inscription)
        
        # Buscar valor da inscrição
        event = await self.db.get(Event, self.event_id)
        
        if event.inscription_price > 0:
            # Gerar pagamento PIX
            try:
                payment_result = await self.payment_manager.create_payment(
                    amount=event.inscription_price,
                    description=f"Inscrição - {event.name} - {self.team_name.value}",
                    payer_info={
                        'reference_id': f"inscription_{inscription.id}",
                        'name': interaction.user.display_name,
                        'email': f"{interaction.user.id}@discord.user"
                    }
                )
                
                # Salvar pagamento no banco
                payment = Payment(
                    inscription_id=inscription.id,
                    user_id=str(interaction.user.id),
                    amount=event.inscription_price,
                    pix_code=payment_result.get('brcode'),
                    qrcode_url=payment_result.get('qrcode_image'),
                    external_id=payment_result.get('id'),
                    status=PaymentStatus.PENDING,
                    expires_at=datetime.now() + timedelta(minutes=PaymentConfig.PIX_EXPIRATION_MINUTES)
                )
                
                self.db.add(payment)
                await self.db.commit()
                
                # Enviar informações de pagamento
                embed = create_payment_embed(
                    event_name=event.name,
                    team_name=self.team_name.value,
                    amount=event.inscription_price,
                    pix_code=payment_result.get('brcode'),
                    qrcode_url=payment_result.get('qrcode_image'),
                    expires_at=payment.expires_at
                )
                
                view = PaymentView(payment.id, self.payment_manager, self.db)
                
                await interaction.followup.send(
                    f"{BotConfig.EMOJIS['check']} Inscrição registrada! Complete o pagamento:",
                    embed=embed,
                    view=view,
                    ephemeral=True
                )
                
                # Iniciar verificação automática
                asyncio.create_task(auto_check_payment(payment.id, self.db, self.payment_manager))
                
            except Exception as e:
                await interaction.followup.send(
                    Messages.error(f"Erro ao gerar pagamento: {str(e)}"),
                    ephemeral=True
                )
        else:
            # Inscrição gratuita
            inscription.approved = True
            inscription.paid = True
            await self.db.commit()
            
            await interaction.followup.send(
                Messages.success(f"Inscrição do time **{self.team_name.value}** realizada com sucesso!"),
                ephemeral=True
            )

class PaymentView(discord.ui.View):
    """View com botões para gerenciar pagamento"""
    
    def __init__(self, payment_id: int, payment_manager: PaymentManager, db_session):
        super().__init__(timeout=None)
        self.payment_id = payment_id
        self.payment_manager = payment_manager
        self.db = db_session
    
    @discord.ui.button(label="Copiar PIX", style=discord.ButtonStyle.primary, emoji="📋")
    async def copy_pix(self, interaction: discord.Interaction, button: discord.ui.Button):
        payment = await self.db.get(Payment, self.payment_id)
        if payment and payment.pix_code:
            await interaction.response.send_message(
                f"```{payment.pix_code}```\nCopie o código acima e cole no app do seu banco!",
                ephemeral=True
            )
    
    @discord.ui.button(label="Verificar Pagamento", style=discord.ButtonStyle.success, emoji="✅")
    async def check_payment(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        payment = await self.db.get(Payment, self.payment_id)
        if not payment:
            await interaction.followup.send(Messages.error("Pagamento não encontrado!"))
            return
        
        # Verificar status na API
        try:
            status = await self.payment_manager.check_payment(payment.external_id)
            
            if status.upper() in ['COMPLETED', 'APPROVED', 'CONFIRMED']:
                payment.status = PaymentStatus.APPROVED
                payment.paid_at = datetime.now()
                
                # Aprovar inscrição
                inscription = await self.db.get(Inscription, payment.inscription_id)
                inscription.paid = True
                inscription.approved = True
                
                await self.db.commit()
                
                await interaction.followup.send(
                    f"{BotConfig.EMOJIS['check']} {BotConfig.EMOJIS['money']} **Pagamento confirmado!**\n"
                    f"Sua inscrição foi aprovada com sucesso!",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"{BotConfig.EMOJIS['aviso']} Pagamento ainda pendente. Aguarde alguns instantes após realizar o PIX.",
                    ephemeral=True
                )
        except Exception as e:
            await interaction.followup.send(
                Messages.error(f"Erro ao verificar pagamento: {str(e)}"),
                ephemeral=True
            )
    
    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.danger, emoji="❌")
    async def cancel_payment(self, interaction: discord.Interaction, button: discord.ui.Button):
        payment = await self.db.get(Payment, self.payment_id)
        if payment:
            payment.status = PaymentStatus.CANCELLED
            inscription = await self.db.get(Inscription, payment.inscription_id)
            self.db.delete(inscription)
            await self.db.commit()
            
            await interaction.response.send_message(
                Messages.warning("Inscrição cancelada."),
                ephemeral=True
            )

async def auto_check_payment(payment_id: int, db_session, payment_manager: PaymentManager):
    """Verifica automaticamente o pagamento a cada 30 segundos"""
    
    for _ in range(60):  # 30 minutos de verificação
        await asyncio.sleep(30)
        
        payment = await db_session.get(Payment, payment_id)
        if not payment or payment.status != PaymentStatus.PENDING:
            break
        
        try:
            status = await payment_manager.check_payment(payment.external_id)
            
            if status.upper() in ['COMPLETED', 'APPROVED', 'CONFIRMED']:
                payment.status = PaymentStatus.APPROVED
                payment.paid_at = datetime.now()
                
                inscription = await db_session.get(Inscription, payment.inscription_id)
                inscription.paid = True
                inscription.approved = True
                
                await db_session.commit()
                
                # Aqui você pode enviar uma DM para o usuário notificando
                break
        except:
            continue

class InscriptionsCog(commands.Cog):
    """Sistema completo de inscrições com pagamento PIX"""
    
    def __init__(self, bot):
        self.bot = bot
        self.payment_manager = PaymentManager(provider="openpix")  # ou "mercadopago"
    
    @app_commands.command(name="abrir_inscricoes", description="Abre inscrições para um evento")
    @app_commands.describe(
        evento="Nome do evento",
        vagas="Número de vagas disponíveis",
        valor="Valor da inscrição em reais (0 para gratuito)",
        data_limite="Data limite (formato: DD/MM/YYYY HH:MM)"
    )
    async def abrir_inscricoes(
        self,
        interaction: discord.Interaction,
        evento: str,
        vagas: int,
        valor: float = 0.0,
        data_limite: Optional[str] = None
    ):
        # Verificar permissões
        if not self.bot.is_vip_or_owner(interaction.user):
            await interaction.response.send_message(
                Messages.error(Messages.VIP_ONLY + Messages.CONTACT_OWNER),
                ephemeral=True
            )
            return
        
        # Buscar evento no banco
        # (implementar lógica de busca)
        
        # Criar embed de inscrições
        embed = discord.Embed(
            title=f"{BotConfig.EMOJIS['trophy']} INSCRIÇÕES ABERTAS",
            description=f"**Evento:** {evento}\n"
                       f"**Vagas:** {vagas}\n"
                       f"**Valor:** {'Gratuito' if valor == 0 else f'R$ {valor:.2f}'}\n"
                       f"**Prazo:** {data_limite or 'Sem prazo definido'}",
            color=BotConfig.COLORS['success']
        )
        
        embed.add_field(
            name="📋 Como se inscrever",
            value="Clique no botão abaixo e preencha o formulário!",
            inline=False
        )
        
        if valor > 0:
            embed.add_field(
                name=f"{BotConfig.EMOJIS['money']} Pagamento",
                value="Após preencher, você receberá o código PIX para pagamento.\n"
                      "A confirmação é automática!",
                inline=False
            )
        
        view = InscriptionButton(evento, valor)
        
        await interaction.response.send_message(embed=embed, view=view)
    
    @app_commands.command(name="listar_inscricoes", description="Lista todas as inscrições de um evento")
    async def listar_inscricoes(self, interaction: discord.Interaction, evento: str):
        # Implementar listagem
        pass
    
    @app_commands.command(name="aprovar_inscricao", description="Aprova uma inscrição manualmente")
    async def aprovar_inscricao(self, interaction: discord.Interaction, inscricao_id: int):
        # Implementar aprovação manual
        pass
    
    @app_commands.command(name="sortear_chaves", description="Sorteia as chaves do torneio")
    async def sortear_chaves(self, interaction: discord.Interaction, evento: str):
        # Implementar sorteio
        pass

class InscriptionButton(discord.ui.View):
    """Botão para abrir modal de inscrição"""
    
    def __init__(self, event_name: str, price: float):
        super().__init__(timeout=None)
        self.event_name = event_name
        self.price = price
    
    @discord.ui.button(label="Inscrever-se", style=discord.ButtonStyle.success, emoji="✍️")
    async def inscribe(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Abrir modal
        modal = InscriptionModal(1, None, None)  # Passar event_id real e db
        await interaction.response.send_modal(modal)

async def setup(bot):
    await bot.add_cog(InscriptionsCog(bot))
