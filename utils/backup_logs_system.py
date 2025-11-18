"""
Sistema de Backup Automático e Logs Detalhados
"""

import discord
from discord.ext import commands, tasks
import aiofiles
import asyncio
import shutil
import os
from datetime import datetime, timedelta
from pathlib import Path
import json
import gzip
from typing import Optional
from loguru import logger

from config import DatabaseConfig, LogConfig
from database.models import Log, Backup

# =============================================
# CONFIGURAÇÃO DO LOGURU
# =============================================

# Remover handler padrão
logger.remove()

# Adicionar handler para arquivo com rotação
logger.add(
    LogConfig.LOG_FILE,
    format=LogConfig.LOG_FORMAT,
    level=LogConfig.LOG_LEVEL,
    rotation=LogConfig.LOG_ROTATION,
    retention=LogConfig.LOG_RETENTION,
    compression="zip"
)

# Adicionar handler para console
logger.add(
    lambda msg: print(msg, end=""),
    format=LogConfig.LOG_FORMAT,
    level="INFO",
    colorize=True
)

# =============================================
# GERENCIADOR DE BACKUPS
# =============================================

class BackupManager:
    """Gerencia backups automáticos do banco de dados"""
    
    def __init__(self, bot):
        self.bot = bot
        self.backup_dir = Path(DatabaseConfig.BACKUP_PATH)
        self.backup_dir.mkdir(exist_ok=True)
    
    async def create_backup(self, compress: bool = True) -> Optional[str]:
        """
        Cria backup do banco de dados
        
        Returns:
            Caminho do arquivo de backup ou None se falhar
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"backup_{timestamp}.db"
        backup_path = self.backup_dir / backup_name
        
        try:
            # Copiar arquivo do banco
            source_db = "tournament_bot.db"
            shutil.copy2(source_db, backup_path)
            
            logger.info(f"Backup criado: {backup_path}")
            
            # Comprimir se solicitado
            if compress:
                compressed_path = backup_path.with_suffix('.db.gz')
                
                with open(backup_path, 'rb') as f_in:
                    with gzip.open(compressed_path, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                
                # Remover arquivo não comprimido
                backup_path.unlink()
                backup_path = compressed_path
                
                logger.info(f"Backup comprimido: {compressed_path}")
            
            # Registrar no banco
            file_size = backup_path.stat().st_size
            backup_record = Backup(
                filename=backup_path.name,
                filepath=str(backup_path),
                size_bytes=file_size
            )
            
            # Adicionar ao banco (implementar com session)
            
            return str(backup_path)
        
        except Exception as e:
            logger.error(f"Erro ao criar backup: {e}")
            return None
    
    async def restore_backup(self, backup_path: str) -> bool:
        """
        Restaura banco de dados de um backup
        
        Args:
            backup_path: Caminho do arquivo de backup
            
        Returns:
            True se restaurado com sucesso
        """
        try:
            backup_file = Path(backup_path)
            
            if not backup_file.exists():
                logger.error(f"Arquivo de backup não encontrado: {backup_path}")
                return False
            
            # Descomprimir se necessário
            if backup_file.suffix == '.gz':
                temp_path = backup_file.with_suffix('')
                
                with gzip.open(backup_file, 'rb') as f_in:
                    with open(temp_path, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                
                source = temp_path
            else:
                source = backup_file
            
            # Fazer backup do arquivo atual antes de restaurar
            current_db = "tournament_bot.db"
            safety_backup = f"{current_db}.before_restore"
            shutil.copy2(current_db, safety_backup)
            
            # Restaurar
            shutil.copy2(source, current_db)
            
            # Limpar temporários
            if backup_file.suffix == '.gz':
                temp_path.unlink()
            
            logger.success(f"Banco de dados restaurado de: {backup_path}")
            return True
        
        except Exception as e:
            logger.error(f"Erro ao restaurar backup: {e}")
            return False
    
    async def cleanup_old_backups(self, keep_days: int = 30):
        """Remove backups mais antigos que N dias"""
        cutoff_date = datetime.now() - timedelta(days=keep_days)
        
        removed = 0
        for backup_file in self.backup_dir.glob("backup_*.db*"):
            # Extrair data do nome do arquivo
            try:
                date_str = backup_file.stem.split('_')[1]  # YYYYMMDD
                backup_date = datetime.strptime(date_str, "%Y%m%d")
                
                if backup_date < cutoff_date:
                    backup_file.unlink()
                    removed += 1
                    logger.info(f"Backup antigo removido: {backup_file.name}")
            
            except:
                continue
        
        logger.info(f"{removed} backups antigos removidos")
    
    async def list_backups(self) -> list:
        """Lista todos os backups disponíveis"""
        backups = []
        
        for backup_file in sorted(self.backup_dir.glob("backup_*.db*"), reverse=True):
            size_mb = backup_file.stat().st_size / (1024 * 1024)
            
            backups.append({
                'filename': backup_file.name,
                'path': str(backup_file),
                'size_mb': round(size_mb, 2),
                'created': datetime.fromtimestamp(backup_file.stat().st_ctime)
            })
        
        return backups

# =============================================
# SISTEMA DE LOGS
# =============================================

class LogManager:
    """Gerencia logs de ações do bot"""
    
    def __init__(self, bot):
        self.bot = bot
    
    async def log_action(
        self,
        guild_id: str,
        action: str,
        user_id: Optional[str] = None,
        details: dict = None
    ):
        """
        Registra uma ação no banco de dados e no arquivo de log
        
        Args:
            guild_id: ID do servidor
            action: Nome da ação (ex: "event_created", "match_completed")
            user_id: ID do usuário que executou a ação
            details: Detalhes adicionais em formato dict
        """
        # Log no arquivo
        logger.info(f"[{guild_id}] {action} by {user_id}: {details}")
        
        # Salvar no banco
        log_entry = Log(
            guild_id=guild_id,
            action=action,
            user_id=user_id,
            details=details or {}
        )
        
        # Adicionar ao banco (implementar com session)
    
    async def send_log_to_channel(
        self,
        guild: discord.Guild,
        action: str,
        user: discord.User,
        details: str,
        color: int = 0x00FF00
    ):
        """Envia log para um canal específico do Discord"""
        
        # Buscar canal de logs (configurável por servidor)
        log_channel_id = None  # Buscar do DB por guild_id
        
        if not log_channel_id:
            return
        
        log_channel = guild.get_channel(int(log_channel_id))
        if not log_channel:
            return
        
        embed = discord.Embed(
            title=f"📋 {action}",
            description=details,
            color=color,
            timestamp=datetime.now()
        )
        
        embed.set_author(
            name=user.display_name,
            icon_url=user.avatar.url if user.avatar else None
        )
        
        embed.set_footer(text=f"User ID: {user.id}")
        
        try:
            await log_channel.send(embed=embed)
        except:
            pass

# =============================================
# DECORATORS PARA LOG AUTOMÁTICO
# =============================================

def log_command(action_name: str):
    """Decorator para logar comandos automaticamente"""
    def decorator(func):
        async def wrapper(self, interaction: discord.Interaction, *args, **kwargs):
            # Executar comando
            result = await func(self, interaction, *args, **kwargs)
            
            # Logar ação
            if hasattr(self, 'bot') and hasattr(self.bot, 'log_manager'):
                await self.bot.log_manager.log_action(
                    guild_id=str(interaction.guild_id),
                    action=action_name,
                    user_id=str(interaction.user.id),
                    details={
                        'command': func.__name__,
                        'args': str(args),
                        'kwargs': str(kwargs)
                    }
                )
            
            return result
        
        return wrapper
    return decorator

# =============================================
# COG PARA COMANDOS DE BACKUP
# =============================================

class BackupCog(commands.Cog):
    """Comandos de backup e manutenção"""
    
    def __init__(self, bot):
        self.bot = bot
        self.backup_manager = BackupManager(bot)
        self.auto_backup_task.start()
    
    def cog_unload(self):
        self.auto_backup_task.cancel()
    
    @tasks.loop(hours=24)
    async def auto_backup_task(self):
        """Task que roda automaticamente a cada 24 horas"""
        logger.info("Iniciando backup automático...")
        
        backup_path = await self.backup_manager.create_backup(compress=True)
        
        if backup_path:
            logger.success(f"Backup automático concluído: {backup_path}")
            
            # Limpar backups antigos
            await self.backup_manager.cleanup_old_backups(keep_days=30)
        else:
            logger.error("Falha no backup automático!")
    
    @auto_backup_task.before_loop
    async def before_auto_backup(self):
        await self.bot.wait_until_ready()
    
    @commands.command(name="backup")
    @commands.is_owner()
    async def manual_backup(self, ctx):
        """Cria backup manual do banco de dados"""
        await ctx.send("🔄 Criando backup...")
        
        backup_path = await self.backup_manager.create_backup(compress=True)
        
        if backup_path:
            file_size = Path(backup_path).stat().st_size / (1024 * 1024)
            await ctx.send(
                f"✅ Backup criado com sucesso!\n"
                f"📁 Arquivo: `{Path(backup_path).name}`\n"
                f"📊 Tamanho: {file_size:.2f} MB"
            )
        else:
            await ctx.send("❌ Erro ao criar backup!")
    
    @commands.command(name="list_backups")
    @commands.is_owner()
    async def list_backups(self, ctx):
        """Lista todos os backups disponíveis"""
        backups = await self.backup_manager.list_backups()
        
        if not backups:
            await ctx.send("Nenhum backup encontrado.")
            return
        
        embed = discord.Embed(
            title="📦 Backups Disponíveis",
            color=0x00FF00
        )
        
        for backup in backups[:10]:  # Mostrar até 10
            embed.add_field(
                name=backup['filename'],
                value=f"**Tamanho:** {backup['size_mb']} MB\n"
                      f"**Criado:** {backup['created'].strftime('%d/%m/%Y %H:%M')}",
                inline=False
            )
        
        await ctx.send(embed=embed)
    
    @commands.command(name="restore")
    @commands.is_owner()
    async def restore_backup(self, ctx, filename: str):
        """Restaura banco de dados de um backup"""
        await ctx.send(f"⚠️ Restaurando backup `{filename}`...")
        
        backup_path = DatabaseConfig.BACKUP_PATH + filename
        success = await self.backup_manager.restore_backup(backup_path)
        
        if success:
            await ctx.send("✅ Banco de dados restaurado! Reinicie o bot.")
        else:
            await ctx.send("❌ Erro ao restaurar backup!")

# =============================================
# COG PARA GERENCIAR CANAL DE LOGS
# =============================================

class LogChannelCog(commands.Cog):
    """Comandos para configurar canal de logs"""
    
    def __init__(self, bot):
        self.bot = bot
        self.log_manager = LogManager(bot)
    
    @commands.command(name="setlog")
    @commands.has_permissions(administrator=True)
    async def set_log_channel(self, ctx, channel: discord.TextChannel):
        """Define canal para receber logs do bot"""
        
        # Salvar no banco de dados (implementar)
        # guild_config['log_channel_id'] = channel.id
        
        await ctx.send(f"✅ Canal de logs definido: {channel.mention}")
        
        # Enviar mensagem de teste
        await self.log_manager.send_log_to_channel(
            guild=ctx.guild,
            action="Canal de Logs Configurado",
            user=ctx.author,
            details=f"O canal {channel.mention} foi configurado para receber logs.",
            color=0x00FF00
        )
    
    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        """Log quando canal é criado"""
        await self.log_manager.send_log_to_channel(
            guild=channel.guild,
            action="Canal Criado",
            user=self.bot.user,
            details=f"**Canal:** {channel.mention}\n**Tipo:** {channel.type}",
            color=0x00FF00
        )
    
    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        """Log quando canal é deletado"""
        await self.log_manager.send_log_to_channel(
            guild=channel.guild,
            action="Canal Deletado",
            user=self.bot.user,
            details=f"**Canal:** {channel.name}\n**Tipo:** {channel.type}",
            color=0xFF0000
        )
    
    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Log quando membro entra"""
        await self.log_manager.send_log_to_channel(
            guild=member.guild,
            action="Membro Entrou",
            user=member,
            details=f"{member.mention} entrou no servidor.",
            color=0x00FF00
        )
    
    @commands.Cog.listener()
    async def on_member_remove(self, member):
        """Log quando membro sai"""
        await self.log_manager.send_log_to_channel(
            guild=member.guild,
            action="Membro Saiu",
            user=member,
            details=f"**{member.display_name}** saiu do servidor.",
            color=0xFF0000
        )

async def setup(bot):
    await bot.add_cog(BackupCog(bot))
    await bot.add_cog(LogChannelCog(bot))

# =============================================
# EXEMPLO DE USO DO SISTEMA DE LOGS
# =============================================

"""
# No seu comando, use assim:

@log_command("event_created")
async def criar_evento(self, interaction, nome: str):
    # Seu código aqui
    pass

# Ou manualmente:

await self.bot.log_manager.log_action(
    guild_id=str(interaction.guild_id),
    action="match_completed",
    user_id=str(interaction.user.id),
    details={
        'match_id': 123,
        'winner': 'Team A',
        'score': '2-1'
    }
)

# Para enviar log visual no canal:

await self.bot.log_manager.send_log_to_channel(
    guild=interaction.guild,
    action="Confronto Finalizado",
    user=interaction.user,
    details=f"**Vencedor:** Team A\n**Placar:** 2-1",
    color=0xFFD700
)
"""
