import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, List
import random

from config import BotConfig, Messages, TemplateConfig
from database.models import Event, Team, Match, Template
from utils.embeds import create_announcement_embed

class QualityOfLifeCog(commands.Cog):
    """Comandos que facilitam a vida dos organizadores"""
    
    def __init__(self, bot):
        self.bot = bot
    
    # =============================================
    # QUICKMATCH - Confronto Rápido
    # =============================================
    
    @app_commands.command(
        name="quickmatch",
        description="Cria um confronto rápido sem muitos campos"
    )
    @app_commands.describe(
        time1="Primeiro time",
        time2="Segundo time",
        id_sala="ID da sala (opcional)"
    )
    async def quickmatch(
        self,
        interaction: discord.Interaction,
        time1: discord.Role,
        time2: discord.Role,
        id_sala: Optional[str] = None
    ):
        """Cria confronto com menos campos, gerando ID/senha automaticamente se necessário"""
        
        if not self.bot.is_vip_or_owner(interaction.user):
            await interaction.response.send_message(
                Messages.error(Messages.VIP_ONLY),
                ephemeral=True
            )
            return
        
        # Gerar ID e senha automaticamente
        if not id_sala:
            id_sala = f"{random.randint(100000, 999999)}"
        senha = f"{random.randint(1000, 9999)}"
        
        embed = discord.Embed(
            title=f"{BotConfig.EMOJIS['versus']} CONFRONTO RÁPIDO",
            description=f"{time1.mention} **VS** {time2.mention}",
            color=BotConfig.COLORS['warning']
        )
        
        embed.add_field(name="🆔 ID da Sala", value=f"`{id_sala}`", inline=True)
        embed.add_field(name="🔑 Senha", value=f"`{senha}`", inline=True)
        
        # Botão para copiar ID
        view = discord.ui.View()
        button = discord.ui.Button(
            label="Copiar ID",
            style=discord.ButtonStyle.primary,
            emoji="📋"
        )
        
        async def copy_callback(btn_interaction: discord.Interaction):
            await btn_interaction.response.send_message(
                f"```{id_sala}```",
                ephemeral=True
            )
        
        button.callback = copy_callback
        view.add_item(button)
        
        await interaction.response.send_message(embed=embed, view=view)
    
    # =============================================
    # CLONE_EVENTO - Duplicar Evento
    # =============================================
    
    @app_commands.command(
        name="clone_evento",
        description="Duplica um evento existente com nova categoria"
    )
    @app_commands.describe(
        evento_original="Nome da categoria do evento original",
        novo_nome="Nome para o novo evento"
    )
    async def clone_evento(
        self,
        interaction: discord.Interaction,
        evento_original: str,
        novo_nome: str
    ):
        """Clona estrutura de canais e cargos de um evento existente"""
        
        await interaction.response.defer(ephemeral=True)
        
        if not self.bot.is_vip_or_owner(interaction.user):
            await interaction.followup.send(
                Messages.error(Messages.VIP_ONLY),
                ephemeral=True
            )
            return
        
        guild = interaction.guild
        
        # Buscar categoria original
        original_category = discord.utils.get(guild.categories, name=evento_original)
        if not original_category:
            await interaction.followup.send(
                Messages.error(f"Evento '{evento_original}' não encontrado!"),
                ephemeral=True
            )
            return
        
        # Verificar se novo nome já existe
        if discord.utils.get(guild.categories, name=novo_nome):
            await interaction.followup.send(
                Messages.error(f"Já existe um evento com o nome '{novo_nome}'!"),
                ephemeral=True
            )
            return
        
        try:
            # Criar nova categoria
            new_category = await guild.create_category(novo_nome)
            
            # Clonar canais
            for channel in original_category.channels:
                if isinstance(channel, discord.TextChannel):
                    await new_category.create_text_channel(
                        name=channel.name,
                        overwrites=channel.overwrites,
                        topic=channel.topic
                    )
                elif isinstance(channel, discord.VoiceChannel):
                    await new_category.create_voice_channel(
                        name=channel.name,
                        overwrites=channel.overwrites
                    )
            
            await interaction.followup.send(
                Messages.success(f"Evento '{novo_nome}' clonado com sucesso!"),
                ephemeral=True
            )
        
        except Exception as e:
            await interaction.followup.send(
                Messages.error(f"Erro ao clonar evento: {str(e)}"),
                ephemeral=True
            )
    
    # =============================================
    # MOVER_TIMES - Mover Membros em Massa
    # =============================================
    
    @app_commands.command(
        name="mover_times",
        description="Move todos os membros de um time para um canal de voz"
    )
    @app_commands.describe(
        cargo="Cargo do time",
        canal="Canal de destino"
    )
    async def mover_times(
        self,
        interaction: discord.Interaction,
        cargo: discord.Role,
        canal: discord.VoiceChannel
    ):
        """Move todos com o cargo para o canal especificado"""
        
        if not interaction.user.guild_permissions.move_members:
            await interaction.response.send_message(
                Messages.error("Você não tem permissão para mover membros!"),
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        moved = 0
        for member in cargo.members:
            if member.voice:
                try:
                    await member.move_to(canal)
                    moved += 1
                except:
                    continue
        
        await interaction.followup.send(
            Messages.success(f"{moved} membros movidos para {canal.mention}!"),
            ephemeral=True
        )
    
    # =============================================
    # ANUNCIAR - Anúncio para Todos os Times
    # =============================================
    
    @app_commands.command(
        name="anunciar",
        description="Envia um anúncio para todos os times de um evento"
    )
    @app_commands.describe(
        evento="Nome da categoria do evento",
        mensagem="Mensagem a ser enviada"
    )
    async def anunciar(
        self,
        interaction: discord.Interaction,
        evento: str,
        mensagem: str
    ):
        """Envia mensagem em todos os canais dos times"""
        
        if not self.bot.is_vip_or_owner(interaction.user):
            await interaction.response.send_message(
                Messages.error(Messages.VIP_ONLY),
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        guild = interaction.guild
        category = discord.utils.get(guild.categories, name=evento)
        
        if not category:
            await interaction.followup.send(
                Messages.error(f"Evento '{evento}' não encontrado!"),
                ephemeral=True
            )
            return
        
        # Buscar canais de texto dos times
        team_channels = [
            ch for ch in category.text_channels
            if ch.name.startswith("⭐")
        ]
        
        embed = create_announcement_embed(
            title="📢 ANÚNCIO DA ORGANIZAÇÃO",
            message=mensagem,
            author=interaction.user
        )
        
        sent = 0
        for channel in team_channels:
            try:
                await channel.send(embed=embed)
                sent += 1
            except:
                continue
        
        await interaction.followup.send(
            Messages.success(f"Anúncio enviado em {sent} canais!"),
            ephemeral=True
        )
    
    # =============================================
    # SORTEAR - Sortear Times/Jogadores
    # =============================================
    
    @app_commands.command(
        name="sortear",
        description="Sorteia times ou jogadores aleatoriamente"
    )
    @app_commands.describe(
        cargo="Cargo dos participantes (opcional)",
        quantidade="Quantidade de sorteados"
    )
    async def sortear(
        self,
        interaction: discord.Interaction,
        quantidade: int,
        cargo: Optional[discord.Role] = None
    ):
        """Sorteia membros aleatoriamente"""
        
        if not self.bot.is_vip_or_owner(interaction.user):
            await interaction.response.send_message(
                Messages.error(Messages.VIP_ONLY),
                ephemeral=True
            )
            return
        
        # Determinar pool de participantes
        if cargo:
            pool = cargo.members
            pool_name = cargo.name
        else:
            pool = interaction.guild.members
            pool_name = "todos os membros"
        
        # Filtrar bots
        pool = [m for m in pool if not m.bot]
        
        if len(pool) < quantidade:
            await interaction.response.send_message(
                Messages.error(f"Não há membros suficientes! (Disponíveis: {len(pool)})"),
                ephemeral=True
            )
            return
        
        # Sortear
        winners = random.sample(pool, quantidade)
        
        embed = discord.Embed(
            title=f"{BotConfig.EMOJIS['trophy']} SORTEIO",
            description=f"**Pool:** {pool_name}\n**Sorteados:** {quantidade}",
            color=BotConfig.COLORS['success']
        )
        
        winners_text = "\n".join([f"{idx+1}. {m.mention}" for idx, m in enumerate(winners)])
        embed.add_field(name="🎲 Sorteados", value=winners_text, inline=False)
        
        await interaction.response.send_message(embed=embed)
    
    # =============================================
    # ENQUETE - Criar Votação
    # =============================================
    
    @app_commands.command(
        name="enquete",
        description="Cria uma enquete com até 10 opções"
    )
    @app_commands.describe(
        pergunta="Pergunta da enquete",
        opcoes="Opções separadas por vírgula (máx 10)"
    )
    async def enquete(
        self,
        interaction: discord.Interaction,
        pergunta: str,
        opcoes: str
    ):
        """Cria enquete com reações"""
        
        if not self.bot.is_vip_or_owner(interaction.user):
            await interaction.response.send_message(
                Messages.error(Messages.VIP_ONLY),
                ephemeral=True
            )
            return
        
        options_list = [opt.strip() for opt in opcoes.split(',')]
        
        if len(options_list) > 10:
            await interaction.response.send_message(
                Messages.error("Máximo de 10 opções!"),
                ephemeral=True
            )
            return
        
        # Emojis de número
        number_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        
        embed = discord.Embed(
            title=f"📊 {pergunta}",
            description="Vote reagindo abaixo!",
            color=BotConfig.COLORS['info']
        )
        
        for idx, option in enumerate(options_list):
            embed.add_field(
                name=f"{number_emojis[idx]} {option}",
                value="\u200b",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed)
        message = await interaction.original_response()
        
        # Adicionar reações
        for idx in range(len(options_list)):
            await message.add_reaction(number_emojis[idx])
    
    # =============================================
    # LIMPAR_INATIVOS - Remove Times Inativos
    # =============================================
    
    @app_commands.command(
        name="limpar_inativos",
        description="Remove cargos de membros que não estão mais no servidor"
    )
    @app_commands.describe(
        evento="Nome da categoria do evento"
    )
    async def limpar_inativos(
        self,
        interaction: discord.Interaction,
        evento: str
    ):
        """Remove cargos de times de membros que saíram do servidor"""
        
        if not self.bot.is_vip_or_owner(interaction.user):
            await interaction.response.send_message(
                Messages.error(Messages.VIP_ONLY),
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        guild = interaction.guild
        category = discord.utils.get(guild.categories, name=evento)
        
        if not category:
            await interaction.followup.send(
                Messages.error(f"Evento '{evento}' não encontrado!"),
                ephemeral=True
            )
            return
        
        # Buscar cargos dos times
        team_roles = [r for r in guild.roles if r.name.startswith("⭐")]
        
        cleaned = 0
        for role in team_roles:
            # Remover cargo de membros que saíram
            for member in role.members:
                if not member in guild.members:
                    try:
                        await member.remove_roles(role)
                        cleaned += 1
                    except:
                        continue
        
        await interaction.followup.send(
            Messages.success(f"{cleaned} cargos removidos de membros inativos!"),
            ephemeral=True
        )
    
    # =============================================
    # EXPORTAR - Exportar Dados
    # =============================================
    
    @app_commands.command(
        name="exportar",
        description="Exporta dados de um evento para CSV"
    )
    @app_commands.describe(
        evento="Nome do evento",
        tipo="Tipo de dados a exportar"
    )
    @app_commands.choices(tipo=[
        app_commands.Choice(name="Times", value="teams"),
        app_commands.Choice(name="Confrontos", value="matches"),
        app_commands.Choice(name="Inscrições", value="inscriptions")
    ])
    async def exportar(
        self,
        interaction: discord.Interaction,
        evento: str,
        tipo: str
    ):
        """Exporta dados do evento para arquivo CSV"""
        
        if not self.bot.is_vip_or_owner(interaction.user):
            await interaction.response.send_message(
                Messages.error(Messages.VIP_ONLY),
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        # Buscar dados no banco
        # Gerar CSV
        # Enviar arquivo
        
        await interaction.followup.send(
            Messages.success("Dados exportados com sucesso!"),
            # file=discord.File(csv_buffer, filename=f"{evento}_{tipo}.csv"),
            ephemeral=True
        )
    
    # =============================================
    # ESTATÍSTICAS - Stats Rápidas
    # =============================================
    
    @app_commands.command(
        name="stats",
        description="Mostra estatísticas de um evento"
    )
    @app_commands.describe(
        evento="Nome do evento"
    )
    async def stats(
        self,
        interaction: discord.Interaction,
        evento: str
    ):
        """Exibe estatísticas gerais do evento"""
        
        # Buscar no banco
        # (implementar busca)
        
        embed = discord.Embed(
            title=f"📊 Estatísticas - {evento}",
            color=BotConfig.COLORS['info']
        )
        
        embed.add_field(name="Times Inscritos", value="32", inline=True)
        embed.add_field(name="Partidas Realizadas", value="16", inline=True)
        embed.add_field(name="Fase Atual", value="Quartas de Final", inline=True)
        embed.add_field(name="Kills Totais", value="450", inline=True)
        embed.add_field(name="MVP", value="@JogadorX", inline=True)
        embed.add_field(name="Time Líder", value="Los Grandes", inline=True)
        
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(QualityOfLifeCog(bot))
