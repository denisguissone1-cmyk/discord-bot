import discord
from discord import app_commands
from discord.ext import commands
from typing import List, Dict, Optional
import random
import math
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

from config import BotConfig, TournamentPhases
from database.models import Event, Team, Match, Bracket, PhaseType

class BracketGenerator:
    """Gerador de chaveamentos para torneios"""
    
    @staticmethod
    def validate_teams_count(teams_count: int, bracket_type: str) -> bool:
        """Valida se o número de times é válido para o tipo de chaveamento"""
        if bracket_type == "single_elimination":
            # Deve ser potência de 2
            return teams_count > 0 and (teams_count & (teams_count - 1)) == 0
        elif bracket_type == "groups":
            # Múltiplo de 4 (grupos de 4)
            return teams_count >= 8 and teams_count % 4 == 0
        return True
    
    @staticmethod
    def create_single_elimination(teams: List[Team]) -> Dict:
        """
        Cria chaveamento de eliminatória simples
        
        Returns:
            {
                'rounds': [
                    {
                        'name': 'Oitavas de Final',
                        'matches': [
                            {'team1': Team1, 'team2': Team2, 'match_number': 1},
                            ...
                        ]
                    },
                    ...
                ]
            }
        """
        teams_count = len(teams)
        
        # Verificar se é potência de 2
        if not BracketGenerator.validate_teams_count(teams_count, "single_elimination"):
            # Adicionar "bye" (vagas vazias) até a próxima potência de 2
            next_power = 2 ** math.ceil(math.log2(teams_count))
            teams = teams + [None] * (next_power - teams_count)
            teams_count = next_power
        
        # Embaralhar times
        random.shuffle(teams)
        
        rounds = []
        current_teams = teams.copy()
        round_number = 1
        
        while len(current_teams) > 1:
            # Determinar nome da fase
            phase_name = TournamentPhases.get_phase_name(len(current_teams))
            
            matches = []
            for i in range(0, len(current_teams), 2):
                team1 = current_teams[i]
                team2 = current_teams[i + 1] if i + 1 < len(current_teams) else None
                
                matches.append({
                    'team1': team1,
                    'team2': team2,
                    'match_number': len(matches) + 1,
                    'winner': None
                })
            
            rounds.append({
                'name': phase_name,
                'phase': str(len(current_teams)),
                'matches': matches
            })
            
            # Preparar para próxima rodada (vencedores avançam)
            current_teams = [None] * (len(current_teams) // 2)
            round_number += 1
        
        return {'rounds': rounds, 'type': 'single_elimination'}
    
    @staticmethod
    def create_double_elimination(teams: List[Team]) -> Dict:
        """Cria chaveamento de eliminatória dupla (Winners + Losers bracket)"""
        # TODO: Implementar dupla eliminação
        pass
    
    @staticmethod
    def create_groups(teams: List[Team], teams_per_group: int = 4) -> Dict:
        """
        Cria fase de grupos
        
        Returns:
            {
                'groups': [
                    {
                        'name': 'Grupo A',
                        'teams': [Team1, Team2, Team3, Team4],
                        'matches': [...]
                    },
                    ...
                ]
            }
        """
        teams_count = len(teams)
        groups_count = teams_count // teams_per_group
        
        # Embaralhar times
        random.shuffle(teams)
        
        groups = []
        for i in range(groups_count):
            group_letter = chr(65 + i)  # A, B, C, ...
            group_teams = teams[i * teams_per_group:(i + 1) * teams_per_group]
            
            # Criar confrontos do grupo (todos contra todos)
            matches = []
            for j, team1 in enumerate(group_teams):
                for team2 in group_teams[j + 1:]:
                    matches.append({
                        'team1': team1,
                        'team2': team2,
                        'match_number': len(matches) + 1
                    })
            
            groups.append({
                'name': f'Grupo {group_letter}',
                'teams': group_teams,
                'matches': matches
            })
        
        return {'groups': groups, 'type': 'groups'}
    
    @staticmethod
    def create_swiss(teams: List[Team], rounds: int = None) -> Dict:
        """Sistema Suíço - times com pontuação similar enfrentam-se"""
        if rounds is None:
            rounds = math.ceil(math.log2(len(teams)))
        
        # TODO: Implementar sistema suíço
        pass
    
    @staticmethod
    def create_round_robin(teams: List[Team]) -> Dict:
        """Todos contra todos"""
        matches = []
        for i, team1 in enumerate(teams):
            for team2 in teams[i + 1:]:
                matches.append({
                    'team1': team1,
                    'team2': team2,
                    'match_number': len(matches) + 1
                })
        
        return {
            'matches': matches,
            'type': 'round_robin'
        }

class BracketVisualizer:
    """Gera visualização gráfica do chaveamento"""
    
    @staticmethod
    def generate_bracket_image(bracket_data: Dict) -> BytesIO:
        """Gera imagem do chaveamento"""
        
        if bracket_data['type'] == 'single_elimination':
            return BracketVisualizer._draw_single_elimination(bracket_data)
        elif bracket_data['type'] == 'groups':
            return BracketVisualizer._draw_groups(bracket_data)
        
        return None
    
    @staticmethod
    def _draw_single_elimination(bracket_data: Dict) -> BytesIO:
        """Desenha chave de eliminatória simples"""
        
        rounds = bracket_data['rounds']
        
        # Dimensões
        match_height = 60
        match_width = 200
        horizontal_spacing = 100
        vertical_spacing = 20
        
        # Calcular tamanho da imagem
        width = len(rounds) * (match_width + horizontal_spacing) + 100
        max_matches = max(len(r['matches']) for r in rounds)
        height = max_matches * (match_height + vertical_spacing) + 100
        
        # Criar imagem
        img = Image.new('RGB', (width, height), color='#2C2F33')
        draw = ImageDraw.Draw(img)
        
        try:
            font = ImageFont.truetype("arial.ttf", 14)
            title_font = ImageFont.truetype("arial.ttf", 18)
        except:
            font = ImageFont.load_default()
            title_font = ImageFont.load_default()
        
        # Desenhar cada rodada
        x = 50
        for round_idx, round_data in enumerate(rounds):
            # Título da rodada
            draw.text((x, 20), round_data['name'], fill='#FFFFFF', font=title_font)
            
            # Calcular espaçamento vertical para centralizar
            total_matches = len(round_data['matches'])
            spacing_multiplier = 2 ** round_idx
            y_start = 60
            
            for match_idx, match in enumerate(round_data['matches']):
                y = y_start + match_idx * (match_height + vertical_spacing) * spacing_multiplier
                
                # Desenhar caixa do confronto
                draw.rectangle(
                    [(x, y), (x + match_width, y + match_height)],
                    outline='#7289DA',
                    width=2
                )
                
                # Team 1
                team1_name = match['team1'].name if match['team1'] else 'TBD'
                draw.text((x + 10, y + 10), team1_name, fill='#FFFFFF', font=font)
                
                # Linha divisória
                draw.line(
                    [(x, y + match_height // 2), (x + match_width, y + match_height // 2)],
                    fill='#7289DA',
                    width=1
                )
                
                # Team 2
                team2_name = match['team2'].name if match['team2'] else 'TBD'
                draw.text((x + 10, y + match_height // 2 + 10), team2_name, fill='#FFFFFF', font=font)
                
                # Conectar ao próximo round
                if round_idx < len(rounds) - 1:
                    next_x = x + match_width + horizontal_spacing
                    next_y = y_start + (match_idx // 2) * (match_height + vertical_spacing) * (spacing_multiplier * 2)
                    
                    # Linha horizontal
                    draw.line(
                        [(x + match_width, y + match_height // 2), (next_x, y + match_height // 2)],
                        fill='#7289DA',
                        width=2
                    )
                    
                    # Linha vertical conectando aos pares
                    if match_idx % 2 == 1:
                        prev_y = y_start + (match_idx - 1) * (match_height + vertical_spacing) * spacing_multiplier
                        draw.line(
                            [(next_x, prev_y + match_height // 2), (next_x, y + match_height // 2)],
                            fill='#7289DA',
                            width=2
                        )
            
            x += match_width + horizontal_spacing
        
        # Salvar em buffer
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        
        return buffer
    
    @staticmethod
    def _draw_groups(bracket_data: Dict) -> BytesIO:
        """Desenha fase de grupos"""
        # TODO: Implementar visualização de grupos
        pass

class BracketsCog(commands.Cog):
    """Sistema de chaveamento automático"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(
        name="gerar_chave",
        description="Gera chaveamento automático para o evento"
    )
    @app_commands.describe(
        evento="Nome do evento",
        tipo="Tipo de chaveamento",
        sortear="Sortear ordem dos times aleatoriamente"
    )
    @app_commands.choices(tipo=[
        app_commands.Choice(name="Eliminatória Simples", value="single"),
        app_commands.Choice(name="Eliminatória Dupla", value="double"),
        app_commands.Choice(name="Fase de Grupos", value="groups"),
        app_commands.Choice(name="Sistema Suíço", value="swiss"),
        app_commands.Choice(name="Todos contra Todos", value="round_robin")
    ])
    async def gerar_chave(
        self,
        interaction: discord.Interaction,
        evento: str,
        tipo: str,
        sortear: bool = True
    ):
        await interaction.response.defer()
        
        # Verificar permissões
        if not self.bot.is_vip_or_owner(interaction.user):
            await interaction.followup.send(
                Messages.error(Messages.VIP_ONLY),
                ephemeral=True
            )
            return
        
        # Buscar evento e times
        # (implementar busca no DB)
        teams = []  # Lista de times do evento
        
        if len(teams) < 2:
            await interaction.followup.send(
                Messages.error("É necessário pelo menos 2 times para gerar chaveamento!"),
                ephemeral=True
            )
            return
        
        # Gerar chaveamento
        if tipo == "single":
            bracket = BracketGenerator.create_single_elimination(teams)
        elif tipo == "groups":
            bracket = BracketGenerator.create_groups(teams)
        elif tipo == "round_robin":
            bracket = BracketGenerator.create_round_robin(teams)
        else:
            await interaction.followup.send(
                Messages.error("Tipo de chaveamento não implementado ainda!"),
                ephemeral=True
            )
            return
        
        # Gerar imagem
        image_buffer = BracketVisualizer.generate_bracket_image(bracket)
        
        if image_buffer:
            file = discord.File(image_buffer, filename="bracket.png")
            
            embed = discord.Embed(
                title=f"{BotConfig.EMOJIS['trophy']} Chaveamento Gerado",
                description=f"**Evento:** {evento}\n"
                           f"**Times:** {len(teams)}\n"
                           f"**Tipo:** {tipo}",
                color=BotConfig.COLORS['success']
            )
            embed.set_image(url="attachment://bracket.png")
            
            await interaction.followup.send(embed=embed, file=file)
        else:
            await interaction.followup.send(
                Messages.error("Erro ao gerar visualização do chaveamento."),
                ephemeral=True
            )
    
    @app_commands.command(
        name="avancar_fase",
        description="Avança para a próxima fase do torneio"
    )
    @app_commands.describe(
        evento="Nome do evento"
    )
    async def avancar_fase(self, interaction: discord.Interaction, evento: str):
        """Avança para próxima fase baseado nos vencedores"""
        
        # Buscar evento
        # Verificar fase atual
        # Pegar vencedores
        # Gerar nova chave
        # Atualizar banco
        
        pass
    
    @app_commands.command(
        name="simular_chave",
        description="Simula resultados aleatórios para teste"
    )
    async def simular_chave(self, interaction: discord.Interaction, evento: str):
        """Útil para testar o sistema sem jogar as partidas"""
        pass

async def setup(bot):
    await bot.add_cog(BracketsCog(bot))
