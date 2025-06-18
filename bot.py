import discord
from discord.ext import commands
import json
import os
from datetime import datetime, timedelta
import asyncio

from time_tracker import TimeTracker

# Configuración del bot
intents = discord.Intents.default()
intents.voice_states = True
intents.guilds = True
intents.members = True  # Necesario para acceder a información de miembros y roles
intents.message_content = True  # Para evitar warnings

bot = commands.Bot(command_prefix='!', intents=intents)
time_tracker = TimeTracker()


# Rol especial para tiempo ilimitado (se carga desde config.json)
UNLIMITED_TIME_ROLE_ID = None

# Variables para IDs de canales de notificación
NOTIFICATION_CHANNEL_ID = 1385005232685318281
PAUSE_NOTIFICATION_CHANNEL_ID = 1385005232685318282
CANCELLATION_NOTIFICATION_CHANNEL_ID = 1385005232685318284

# Cargar configuración completa desde config.json
config = {}
try:
    with open('config.json', 'r') as f:
        config = json.load(f)
    UNLIMITED_TIME_ROLE_ID = config.get('unlimited_time_role_id')
    if UNLIMITED_TIME_ROLE_ID:
        print(f"✅ Rol de tiempo ilimitado cargado desde config: ID {UNLIMITED_TIME_ROLE_ID}")

    # Cargar IDs de canales de notificación desde config
    notification_channels = config.get('notification_channels', {})
    NOTIFICATION_CHANNEL_ID = notification_channels.get('milestones', 1382195219939852500)
    PAUSE_NOTIFICATION_CHANNEL_ID = notification_channels.get('pauses', 1385005232685318282)
    CANCELLATION_NOTIFICATION_CHANNEL_ID = notification_channels.get('cancellations', 1385005232685318284)
    
    print(f"✅ Canales de notificación cargados:")
    print(f"  - Milestones: {NOTIFICATION_CHANNEL_ID}")
    print(f"  - Pausas: {PAUSE_NOTIFICATION_CHANNEL_ID}")
    print(f"  - Cancelaciones: {CANCELLATION_NOTIFICATION_CHANNEL_ID}")

except Exception as e:
    print(f"⚠️ No se pudo cargar configuración: {e}")
    config = {}
    # Valores por defecto si no se puede cargar config
    NOTIFICATION_CHANNEL_ID = 1385005232685318281
    PAUSE_NOTIFICATION_CHANNEL_ID = 1385005232685318282
    CANCELLATION_NOTIFICATION_CHANNEL_ID = 1385005232685318284

# Task para verificar milestones periódicamente
milestone_check_task = None


@bot.event
async def on_ready():
    print(f'{bot.user} se ha conectado a Discord!')

    # Verificar que el canal de notificaciones existe
    channel = bot.get_channel(NOTIFICATION_CHANNEL_ID)
    if channel:
        if hasattr(channel, 'name'):
            print(f'Canal de notificaciones encontrado: {channel.name} (ID: {channel.id})')
        else:
            print(f'Canal de notificaciones encontrado (ID: {channel.id})')
    else:
        print(f'⚠️ Canal de notificaciones no encontrado con ID: {NOTIFICATION_CHANNEL_ID}')

    try:
        # Sincronización con límite de rate
        synced = await bot.tree.sync()
        print(f'Sincronizados {len(synced)} comando(s) slash')

        # Listar todos los comandos registrados
        commands = [cmd.name for cmd in bot.tree.get_commands()]
        print(f'Comandos registrados: {", ".join(commands)}')

        # Verificar comandos importantes
        if "reiniciar_todos_tiempos" in commands:
            print("✅ Comando reiniciar_todos_tiempos registrado correctamente")
        else:
            print("❌ Comando reiniciar_todos_tiempos no encontrado")

        if "limpiar_base_datos" in commands:
            print("✅ Comando limpiar_base_datos registrado correctamente")
        else:
            print("❌ Comando limpiar_base_datos no encontrado")

    except Exception as e:
        print(f'Error al sincronizar comandos: {e}')

    # Iniciar task de verificación de milestones se hará después de definir la función

# @bot.event
# async def on_voice_state_update(member, before, after):
#     """Función deshabilitada - el seguimiento de tiempo ahora es solo manual"""
#     pass

def is_admin():
    """Decorator para verificar si el usuario tiene permisos de administrador o rol autorizado"""
    async def predicate(interaction: discord.Interaction) -> bool:
        try:
            # Verificar si el usuario es el dueño del servidor o tiene permisos de administrador
            if not hasattr(interaction, 'guild') or not interaction.guild:
                return False

            # Verificar si es el owner del servidor
            if interaction.guild.owner_id == interaction.user.id:
                return True

            member = interaction.guild.get_member(interaction.user.id)
            if not member:
                return False

            # Verificar permisos de administrador
            if member.guild_permissions.administrator:
                return True

            # Verificar si tiene rol autorizado para comandos
            try:
                if has_command_permission_role(member):
                    return True
            except Exception as e:
                print(f"Error verificando rol de permisos: {e}")

            return False

        except Exception as e:
            print(f"Error en verificación de permisos: {e}")
            return False

    return discord.app_commands.check(predicate)

def load_config():
    """Cargar configuración desde config.json"""
    try:
        with open('config.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        print(f"Error cargando configuración: {e}")
        return {}

def has_command_permission_role(member: discord.Member) -> bool:
    """Verificar si el usuario tiene el rol autorizado para usar comandos"""
    config = load_config()
    command_role_id = config.get('command_permission_role_id')

    if command_role_id is None:
        return False

    for role in member.roles:
        if role.id == command_role_id:
            return True
    return False

def can_use_mi_tiempo(member: discord.Member) -> bool:
    """Verificar si el usuario tiene el rol autorizado para usar /mi_tiempo"""
    config = load_config()
    mi_tiempo_role_id = config.get('mi_tiempo_role_id')

    if mi_tiempo_role_id is None:
        return False

    for role in member.roles:
        if role.id == mi_tiempo_role_id:
            return True

    return False

def has_unlimited_time_role(member: discord.Member) -> bool:
    """Verificar si el usuario tiene el rol de tiempo ilimitado"""
    if UNLIMITED_TIME_ROLE_ID is None:
        return False

    for role in member.roles:
        if role.id == UNLIMITED_TIME_ROLE_ID:
            return True
    return False

def calculate_credits(total_seconds: float, has_special_role: bool = False) -> int:
    """Calcular créditos basado en el tiempo total"""
    try:
        # Validar entrada
        if not isinstance(total_seconds, (int, float)) or total_seconds < 0:
            return 0

        total_hours = total_seconds / 3600
        # Lógica actualizada para calcular créditos
        if total_hours >= 2.0:
            return 5  # 2 horas = 5 créditos
        elif total_hours >= 1.0:
            return 3  # 1 hora = 3 créditos
        else:
            return 0  # Menos de 1 hora = 0 créditos

    except Exception as e:
        print(f"Error calculando créditos: {e}")
        return 0



def calculate_credits_from_time(member: discord.Member, time_minutes: int) -> int:
    """Calcular créditos basándose en el tiempo - sistema sin rol únicamente"""
    try:
        # Sin rol: Hasta 1 hora por 3 créditos
        max_time_minutes = 1 * 60  # 60 minutos
        credits_per_session = 3

        # Limitar el tiempo al máximo permitido
        effective_time = min(time_minutes, max_time_minutes)

        # Calcular créditos proporcionales
        if effective_time > 0:
            credits = int((effective_time / max_time_minutes) * credits_per_session)
            return max(1, credits)  # Mínimo 1 crédito

        return 0
    except Exception as e:
        print(f"Error calculando créditos: {e}")
        return 0

@bot.tree.command(name="iniciar_tiempo", description="Iniciar el seguimiento de tiempo para un usuario")
@discord.app_commands.describe(usuario="El usuario para quien iniciar el seguimiento de tiempo")
@is_admin()
async def iniciar_tiempo(interaction: discord.Interaction, usuario: discord.Member):
    if usuario.bot:
        await interaction.response.send_message("❌ No se puede rastrear el tiempo de bots.")
        return

    # Verificar si el usuario tiene el rol de tiempo ilimitado
    has_unlimited_role = has_unlimited_time_role(usuario)

    # Verificar límites según el rol del usuario
    total_time = time_tracker.get_total_time(usuario.id)
    total_hours = total_time / 3600

    if not has_unlimited_role:
        # Usuarios sin rol especial: límite de 1 hora
        if total_hours >= 1.0:
            formatted_time = time_tracker.format_time_human(total_time)
            await interaction.response.send_message(
                f"❌ {usuario.mention} ya ha alcanzado el límite máximo de 1 hora (Tiempo actual: {formatted_time}). "
                f"No se puede iniciar más seguimiento."
            )
            return
    else:
        # Usuarios con rol especial: límite de 4 horas
        if total_hours >= 4.0:
            formatted_time = time_tracker.format_time_human(total_time)
            await interaction.response.send_message(
                f"❌ {usuario.mention} ya ha alcanzado el límite máximo de 4 horas (Tiempo actual: {formatted_time}). "
                f"No se puede iniciar más seguimiento.",

            )
            return

    # Verificar si el usuario tiene tiempo pausado
    user_data = time_tracker.get_user_data(usuario.id)
    if user_data and user_data.get('is_paused', False):
        await interaction.response.send_message(
            f"⚠️ {usuario.mention} tiene tiempo pausado. Usa `/despausar_tiempo` para continuar el tiempo.",

        )
        return

    success = time_tracker.start_tracking(usuario.id, usuario.display_name)
    if success:
        await interaction.response.send_message(f"⏰ El tiempo de {usuario.mention} ha sido iniciado por {interaction.user.mention}")
    else:
        await interaction.response.send_message(f"⚠️ El tiempo de {usuario.mention} ya está activo")

@bot.tree.command(name="pausar_tiempo", description="Pausar el tiempo de un usuario")
@discord.app_commands.describe(usuario="El usuario para quien pausar el tiempo")
@is_admin()
async def pausar_tiempo(interaction: discord.Interaction, usuario: discord.Member):
    # Obtener datos antes de pausar para mostrar tiempo de sesión actual
    user_data = time_tracker.get_user_data(usuario.id)
    total_time_before = time_tracker.get_total_time(usuario.id)

    success = time_tracker.pause_tracking(usuario.id)
    if success:
        # Obtener tiempo total después de pausar (incluye la sesión que se acaba de pausar)
        total_time_after = time_tracker.get_total_time(usuario.id)
        session_time = total_time_after - total_time_before

        # Obtener número de pausas
        pause_count = time_tracker.get_pause_count(usuario.id)

        formatted_total_time = time_tracker.format_time_human(total_time_after)
        formatted_session_time = time_tracker.format_time_human(session_time) if session_time > 0 else "0 Segundos"

        # Verificar si alcanzó 3 pausas para cancelación automática
        if pause_count >= 3:
            # Cancelar automáticamente el tiempo del usuario
            time_tracker.cancel_user_tracking(usuario.id)

            # Respuesta del comando simple para el admin
            await interaction.response.send_message(
                f"⏸️ El tiempo de {usuario.mention} ha sido pausado\n"
                f"🚫 **{usuario.mention} lleva {pause_count} pausas - Tiempo cancelado automáticamente por exceder el límite**"
            )

            # Enviar notificación de cancelación automática
            await send_auto_cancellation_notification(usuario.display_name, formatted_total_time, interaction.user.mention, pause_count)
        else:
            # Respuesta del comando simple para el admin
            await interaction.response.send_message(
                f"⏸️ El tiempo de {usuario.mention} ha sido pausado"
            )

            # Enviar notificación de pausa al canal específico con conteo de pausas
            await send_pause_notification(usuario.display_name, total_time_after, interaction.user.mention, formatted_session_time, pause_count)

    else:
        await interaction.response.send_message(f"⚠️ No hay tiempo activo para {usuario.mention}")

@bot.tree.command(name="despausar_tiempo", description="Despausar el tiempo de un usuario")
@discord.app_commands.describe(usuario="El usuario para quien despausar el tiempo")
@is_admin()
async def despausar_tiempo(interaction: discord.Interaction, usuario: discord.Member):
    # Obtener duración pausada antes de despausar
    paused_duration = time_tracker.get_paused_duration(usuario.id)

    success = time_tracker.resume_tracking(usuario.id)
    if success:
        # Obtener tiempo total después de despausar
        total_time = time_tracker.get_total_time(usuario.id)
        formatted_paused_duration = time_tracker.format_time_human(paused_duration) if paused_duration > 0 else "0 Segundos"

        # Respuesta del comando (efímera para el admin)
        await interaction.response.send_message(
            f"▶️ El tiempo de {usuario.mention} ha sido despausado\n"
            f"**Tiempo pausado:** {formatted_paused_duration}\n"
            f"**Despausado por:** {interaction.user.mention}",

        )

        # Enviar notificación de despausa al canal específico
        await send_unpause_notification(usuario.display_name, total_time, interaction.user.mention, formatted_paused_duration)
    else:
        await interaction.response.send_message(f"⚠️ No se puede despausar - {usuario.mention} no tiene tiempo pausado")

@bot.tree.command(name="sumar_minutos", description="Sumar minutos al tiempo de un usuario")
@discord.app_commands.describe(
    usuario="El usuario al que sumar tiempo",
    minutos="Cantidad de minutos a sumar"
)
@is_admin()
async def sumar_minutos(interaction: discord.Interaction, usuario: discord.Member, minutos: int):
    if minutos <= 0:
        await interaction.response.send_message("❌ La cantidad de minutos debe ser positiva")
        return

    success = time_tracker.add_minutes(usuario.id, usuario.display_name, minutos)
    if success:
        total_time = time_tracker.get_total_time(usuario.id)
        formatted_time = time_tracker.format_time_human(total_time)
        await interaction.response.send_message(
            f"✅ Sumados {minutos} minutos a {usuario.mention} por {interaction.user.mention}\n"
            f"⏱️ Tiempo total: {formatted_time}"
        )
        # Verificar milestone después de sumar tiempo
        await check_time_milestone(usuario.id, usuario.display_name)
    else:
        await interaction.response.send_message(f"❌ Error al sumar tiempo para {usuario.mention}")

@bot.tree.command(name="restar_minutos", description="Restar minutos del tiempo de un usuario")
@discord.app_commands.describe(
    usuario="El usuario al que restar tiempo",
    minutos="Cantidad de minutos a restar"
)
@is_admin()
async def restar_minutos(interaction: discord.Interaction, usuario: discord.Member, minutos: int):
    if minutos <= 0:
        await interaction.response.send_message("❌ La cantidad de minutos debe ser positiva")
        return

    success = time_tracker.subtract_minutes(usuario.id, minutos)
    if success:
        total_time = time_tracker.get_total_time(usuario.id)
        formatted_time = time_tracker.format_time_human(total_time)
        await interaction.response.send_message(
            f"➖ Restados {minutos} minutos de {usuario.mention} por {interaction.user.mention}\n"
            f"⏱️ Tiempo total: {formatted_time}"
        )
    else:
        await interaction.response.send_message(f"❌ Error al restar tiempo para {usuario.mention}")

# Clase para manejar la paginación
class TimesView(discord.ui.View):
    def __init__(self, sorted_users, guild, max_per_page=25):
        super().__init__(timeout=300)  # 5 minutos de timeout
        self.sorted_users = sorted_users
        self.guild = guild
        self.max_per_page = max_per_page
        self.current_page = 0
        self.total_pages = (len(sorted_users) + max_per_page - 1) // max_per_page

        # Deshabilitar botones si solo hay una página
        if self.total_pages <= 1:
            self.clear_items()

    def get_embed(self):
        """Crear embed para la página actual"""
        start_idx = self.current_page * self.max_per_page
        end_idx = min(start_idx + self.max_per_page, len(self.sorted_users))

        current_users = self.sorted_users[start_idx:end_idx]
        user_list = []

        for _, user_id, data in current_users:
            try:
                user_id_int = int(user_id)
                member = self.guild.get_member(user_id_int) if self.guild else None

                # Verificar tipo de membresía
                if member:
                    user_mention = member.mention
                    has_special_role = has_unlimited_time_role(member)
                else:
                    user_name = data.get('name', f'Usuario {user_id}')
                    user_mention = f"**{user_name}** `(ID: {user_id})`"
                    # Usuario no está en el servidor, asumir sin rol especial
                    has_special_role = False

                # Obtener tiempo total
                total_time = time_tracker.get_total_time(user_id_int)
                formatted_time = time_tracker.format_time_human(total_time)

                # Determinar estado
                status = "🔴 Inactivo"
                if data.get('is_active', False):
                    status = "🟢 Activo"
                elif data.get('is_paused', False):
                    total_hours = total_time / 3600
                    if data.get("milestone_completed", False) or (has_special_role and total_hours >= 4.0) or (not has_special_role and total_hours >= 2.0):
                        status = "✅ Terminado"
                    else:
                        status = "⏸️ Pausado"

                # Calcular créditos
                credits = calculate_credits(total_time, has_special_role)
                credit_info = f" 💰 {credits} Créditos" if credits > 0 else ""

                user_list.append(f"📌 {user_mention} - ⏱️ {formatted_time}{credit_info} {status}")

            except Exception as e:
                print(f"Error procesando usuario {user_id}: {e}")
                continue

        embed = discord.Embed(
            title="⏰ Tiempos Registrados",
            description="\n".join(user_list) if user_list else "No hay usuarios en esta página",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )

        embed.set_footer(text=f"Página {self.current_page + 1}/{self.total_pages} • Total: {len(self.sorted_users)} usuarios")
        return embed

    @discord.ui.button(label='◀️ Anterior', style=discord.ButtonStyle.secondary)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1

        # Actualizar estado de botones
        self.update_buttons()

        embed = self.get_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label='▶️ Siguiente', style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1

        # Actualizar estado de botones
        self.update_buttons()

        embed = self.get_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label='📄 Ir a página', style=discord.ButtonStyle.primary)
    async def go_to_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = PageModal(self)
        await interaction.response.send_modal(modal)

    def update_buttons(self):
        """Actualizar estado de los botones según la página actual"""
        # Botón anterior
        self.children[0].disabled = (self.current_page == 0)
        # Botón siguiente  
        self.children[1].disabled = (self.current_page >= self.total_pages - 1)

    async def on_timeout(self):
        """Deshabilitar botones cuando expire el timeout"""
        for item in self.children:
            item.disabled = True

# Modal para ir a una página específica
class PageModal(discord.ui.Modal, title='Ir a Página'):
    def __init__(self, view):
        super().__init__()
        self.view = view

    page_number = discord.ui.TextInput(
        label='Número de página',
        placeholder=f'Ingresa un número entre 1 y {999}',
        required=True,
        max_length=3
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            page = int(self.page_number.value)
            if 1 <= page <= self.view.total_pages:
                self.view.current_page = page - 1
                self.view.update_buttons()
                embed = self.view.get_embed()
                await interaction.response.edit_message(embed=embed, view=self.view)
            else:
                await interaction.response.send_message(
                    f"❌ Página inválida. Debe estar entre 1 y {self.view.total_pages}", 
                    ephemeral=True
                )
        except ValueError:
            await interaction.response.send_message("❌ Por favor ingresa un número válido", ephemeral=True)

@bot.tree.command(name="ver_tiempos", description="Ver todos los tiempos registrados")
@is_admin()
async def ver_tiempos(interaction: discord.Interaction):
    # Responder inmediatamente para evitar timeout
    try:
        await interaction.response.defer(ephemeral=False)
    except Exception as e:
        print(f"Error al defer la interacción: {e}")
        try:
            await interaction.response.send_message("🔄 Procesando tiempos...", ephemeral=False)
        except Exception:
            return

    try:
        # Obtener usuarios con timeout
        tracked_users = await asyncio.wait_for(
            asyncio.to_thread(time_tracker.get_all_tracked_users),
            timeout=5.0
        )

        if not tracked_users:
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("📊 No hay usuarios con tiempo registrado", ephemeral=False)
                else:
                    await interaction.followup.send("📊 No hay usuarios con tiempo registrado")
            except Exception as e:
                print(f"Error enviando mensaje de sin usuarios: {e}")
            return

        # Ordenar usuarios alfabéticamente por nombre
        sorted_users = []
        for user_id, data in tracked_users.items():
            user_name = data.get('name', f'Usuario {user_id}')
            sorted_users.append((user_name.lower(), user_id, data))

        sorted_users.sort(key=lambda x: x[0])

        # Si hay pocos usuarios, usar el método simple (sin paginación)
        if len(sorted_users) <= 25:
            user_list = []
            for _, user_id, data in sorted_users:
                try:
                    user_id_int = int(user_id)
                    member = interaction.guild.get_member(user_id_int) if interaction.guild else None

                    if member:
                        user_mention = member.mention
                        has_special_role = has_unlimited_time_role(member)
                    else:
                        user_name = data.get('name', f'Usuario {user_id}')
                        user_mention = f"**{user_name}** `(ID: {user_id})`"
                        # Verificar tipo de membresía basado en jerarquía de Discord cuando no hay member object

                        has_special_role = False

                    total_time = time_tracker.get_total_time(user_id_int)
                    formatted_time = time_tracker.format_time_human(total_time)

                    status = "🔴 Inactivo"
                    if data.get('is_active', False):
                        status = "🟢 Activo"
                    elif data.get('is_paused', False):
                        total_hours = total_time / 3600
                        if (data.get("milestone_completed", False) or 
                            (has_special_role and total_hours >= 4.0) or 
                            (not has_special_role and total_hours >= 2.0)):
                            status = "✅ Terminado"
                        else:
                            status = "⏸️ Pausado"

                    credits = calculate_credits(total_time, has_special_role)
                    credit_info = f" 💰 {credits} Créditos" if credits > 0 else ""

                    user_list.append(f"📌 {user_mention} - ⏱️ {formatted_time}{credit_info} {status}")

                except Exception as e:
                    print(f"Error procesando usuario {user_id}: {e}")
                    continue

            if not user_list:
                try:
                    if not interaction.response.is_done():
                        await interaction.response.send_message("❌ Error al procesar usuarios registrados", ephemeral=False)
                    else:
                        await interaction.followup.send("❌ Error al procesar usuarios registrados")
                except Exception as e:
                    print(f"Error enviando mensaje de error: {e}")
                return

            # Embed simple sin paginación
            embed = discord.Embed(
                title="⏰ Tiempos Registrados",
                description="\n".join(user_list),
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )
            embed.set_footer(text=f"Total: {len(user_list)} usuarios")

            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed)
            else:
                await interaction.followup.send(embed=embed)
        else:
            # Usar paginación para muchos usuarios
            view = TimesView(sorted_users, interaction.guild, max_per_page=25)
            embed = view.get_embed()

            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, view=view)
            else:
                await interaction.followup.send(embed=embed, view=view)

    except asyncio.TimeoutError:
        error_msg = "❌ Timeout al obtener usuarios. Intenta de nuevo."
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(error_msg, ephemeral=False)
            else:
                await interaction.followup.send(error_msg)
        except Exception as e:
            print(f"Error enviando mensaje de timeout: {e}")

    except Exception as e:
        print(f"Error general en ver_tiempos: {e}")
        import traceback
        traceback.print_exc()

        error_msg = "❌ Error interno del comando. Revisa los logs del servidor."
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(error_msg, ephemeral=False)
            else:
                await interaction.followup.send(error_msg)
        except Exception as e2:
            print(f"No se pudo enviar mensaje de error final: {e2}")

@bot.tree.command(name="reiniciar_tiempo", description="Reiniciar el tiempo de un usuario a cero")
@discord.app_commands.describe(usuario="El usuario cuyo tiempo se reiniciará")
@is_admin()
async def reiniciar_tiempo(interaction: discord.Interaction, usuario: discord.Member):
    success = time_tracker.reset_user_time(usuario.id)
    if success:
        await interaction.response.send_message(f"🔄 Tiempo reiniciado para {usuario.mention} por {interaction.user.mention}")
    else:
        await interaction.response.send_message(f"❌ No se encontró registro de tiempo para {usuario.mention}")

@bot.tree.command(name="reiniciar_todos_tiempos", description="Reiniciar todos los tiempos de todos los usuarios")
@is_admin()
async def reiniciar_todos_tiempos(interaction: discord.Interaction):
    usuarios_reiniciados = time_tracker.reset_all_user_times()
    if usuarios_reiniciados > 0:
        await interaction.response.send_message(f"🔄 Tiempos reiniciados para {usuarios_reiniciados} usuario(s)")
    else:
        await interaction.response.send_message("❌ No hay usuarios con tiempo registrado para reiniciar")

@bot.tree.command(name="limpiar_base_datos", description="ELIMINAR COMPLETAMENTE todos los usuarios registrados de la base de datos")
@is_admin()
async def limpiar_base_datos(interaction: discord.Interaction):
    # Obtener conteo actual de usuarios antes de limpiar
    tracked_users = time_tracker.get_all_tracked_users()
    user_count = len(tracked_users)

    if user_count == 0:
        await interaction.response.send_message("❌ No hay usuarios registrados en la base de datos")
        return

    # Crear embed de confirmación con información detallada
    embed = discord.Embed(
        title="⚠️ CONFIRMACIÓN REQUERIDA",
        description="Esta acción eliminará COMPLETAMENTE todos los datos de usuarios",
        color=discord.Color.red(),
        timestamp=datetime.now()
    )
    embed.add_field(
        name="📊 Datos que se eliminarán:",
        value=f"• {user_count} usuarios registrados\n"
              f"• Todo el historial de tiempo\n"
              f"• Sesiones activas\n"
              f"• Contadores de pausas\n"
              f"• Estados de notificaciones",
        inline=False
    )
    embed.add_field(
        name="⚠️ ADVERTENCIA:",
        value="Esta acción NO se puede deshacer\n"
              "Los usuarios tendrán que registrarse de nuevo",
        inline=False
    )
    embed.add_field(
        name="🔄 Para continuar:",
        value="Usa el comando nuevamente con `confirmar: True`",
        inline=False
    )
    embed.set_footer(text=f"Solicitado por {interaction.user.display_name}")

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="limpiar_base_datos_confirmar", description="CONFIRMAR eliminación completa de la base de datos")
@discord.app_commands.describe(confirmar="Escribe 'SI' para confirmar la eliminación completa")
@is_admin()
async def limpiar_base_datos_confirmar(interaction: discord.Interaction, confirmar: str):
    if confirmar.upper() != "SI":
        await interaction.response.send_message("❌ Operación cancelada. Debes escribir 'SI' para confirmar")
        return

    # Obtener información antes de limpiar
    tracked_users = time_tracker.get_all_tracked_users()
    user_count = len(tracked_users)

    if user_count == 0:
        await interaction.response.send_message("❌ No hay usuarios registrados en la base de datos")
        return

    # Realizar la limpieza completa
    success = time_tracker.clear_all_data()

    if success:
        embed = discord.Embed(
            title="🗑️ BASE DE DATOS LIMPIADA",
            description="Todos los datos de usuarios han sido eliminados completamente",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        embed.add_field(
            name="📊 Datos eliminados:",
            value=f"• {user_count} usuarios registrados\n"
                  f"• Todo el historial de tiempo\n"
                  f"• Sesiones activas\n"
                  f"• Archivo user_times.json reiniciado",
            inline=False
        )
        embed.add_field(
            name="✅ Estado actual:",
            value="Base de datos completamente limpia\n"
                  "Sistema listo para nuevos registros",
            inline=False
        )
        embed.set_footer(text=f"Ejecutado por {interaction.user.display_name}")

        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message("❌ Error al limpiar la base de datos")

@bot.tree.command(name="cancelar_tiempo", description="Cancelar completamente el tiempo de un usuario")
@discord.app_commands.describe(usuario="El usuario cuyo tiempo se cancelará por completo")
@is_admin()
async def cancelar_tiempo(interaction: discord.Interaction, usuario: discord.Member):
    # Obtener el tiempo antes de cancelar
    total_time = time_tracker.get_total_time(usuario.id)
    user_data = time_tracker.get_user_data(usuario.id)

    if user_data:
        formatted_time = time_tracker.format_time_human(total_time)
        success = time_tracker.cancel_user_tracking(usuario.id)
        if success:
            await interaction.response.send_message(
                f"🗑️ El tiempo de {usuario.mention} ha sido cancelado"
            )
            # Enviar notificación al canal de cancelaciones con tiempo cancelado
            await send_cancellation_notification(usuario.display_name, interaction.user.mention, formatted_time)
        else:
            await interaction.response.send_message(f"❌ Error al cancelar el tiempo para {usuario.mention}")
    else:
        await interaction.response.send_message(f"❌ No se encontró registro de tiempo para {usuario.mention}")

@bot.tree.command(name="configurar_canal_tiempos", description="Configurar el canal donde se enviarán las notificaciones de tiempo completado")
@discord.app_commands.describe(canal="El canal donde se enviarán las notificaciones de tiempo completado")
@is_admin()
async def configurar_canal_tiempos(interaction: discord.Interaction, canal: discord.TextChannel):
    global NOTIFICATION_CHANNEL_ID
    NOTIFICATION_CHANNEL_ID = canal.id
    await interaction.response.send_message(f"🎯 Canal de notificaciones de tiempo configurado: {canal.mention}")

@bot.tree.command(name="configurar_canal_pausas", description="Configurar el canal donde se enviarán las notificaciones de pausas")
@discord.app_commands.describe(canal="El canal donde se enviarán las notificaciones de pausas")
@is_admin()
async def configurar_canal_pausas(interaction: discord.Interaction, canal: discord.TextChannel):
    global PAUSE_NOTIFICATION_CHANNEL_ID
    PAUSE_NOTIFICATION_CHANNEL_ID = canal.id
    await interaction.response.send_message(f"⏸️ Canal de notificaciones de pausas configurado: {canal.mention}")
@bot.tree.command(name="configurar_canal_cancelaciones", description="Configurar el canal donde se enviarán las notificaciones de cancelaciones")
@discord.app_commands.describe(canal="El canal donde se enviarán las notificaciones de cancelaciones")
@is_admin()
async def configurar_canal_cancelaciones(interaction: discord.Interaction, canal: discord.TextChannel):
    global CANCELLATION_NOTIFICATION_CHANNEL_ID
    CANCELLATION_NOTIFICATION_CHANNEL_ID = canal.id
    await interaction.response.send_message(f"🗑️ Canal de notificaciones de cancelaciones configurado: {canal.mention}")



@bot.tree.command(name="configurar_canal_despausados", description="Configurar el canal donde se enviarán las notificaciones de despausado")
@discord.app_commands.describe(canal="El canal donde se enviarán las notificaciones cuando alguien sea despausado")
@is_admin()
async def configurar_canal_despausados(interaction: discord.Interaction, canal: discord.TextChannel):
    # Guardar configuración en config.json
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)

        if "notification_channels" not in config:
            config["notification_channels"] = {}

        config["notification_channels"]["unpause"] = canal.id

        with open('config.json', 'w') as f:
            json.dump(config, f, indent=2)

        print(f"✅ Canal de despausados configurado y guardado: {canal.name} (ID: {canal.id})")
    except Exception as e:
        print(f"❌ Error guardando configuración del canal de despausados: {e}")

    await interaction.response.send_message(f"▶️ Canal de notificaciones de despausados configurado: {canal.mention}")

@bot.tree.command(name="configurar_permisos_comandos", description="Configurar qué rol puede usar todos los comandos del bot")
@discord.app_commands.describe(rol="El rol que tendrá permisos para usar todos los comandos del bot")
@is_admin()
async def configurar_permisos_comandos(interaction: discord.Interaction, rol: discord.Role):
    # Guardar configuración en config.json
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)

        config['command_permission_role_id'] = rol.id

        with open('config.json', 'w') as f:
            json.dump(config, f, indent=2)

        print(f"✅ Rol de permisos de comandos configurado y guardado: {rol.name} (ID: {rol.id})")
    except Exception as e:
        print(f"❌ Error guardando configuración del rol de permisos: {e}")

    await interaction.response.send_message(f"🔐 Rol de permisos configurado: {rol.mention}\nLos usuarios con este rol ahora pueden usar todos los comandos del bot.")

@bot.tree.command(name="configurar_mi_tiempo", description="Configurar qué rol puede usar el comando /mi_tiempo")
@discord.app_commands.describe(rol="El rol que podrá usar el comando /mi_tiempo")
@is_admin()
async def configurar_mi_tiempo(interaction: discord.Interaction, rol: discord.Role):
    # Cargar configuración actual
    try:
        config = load_config()

        # Configurar el rol de /mi_tiempo
        config['mi_tiempo_role_id'] = rol.id

        # Guardar configuración
        with open('config.json', 'w') as f:
            json.dump(config, f, indent=2)

        print(f"✅ Rol de /mi_tiempo configurado: {rol.name} (ID: {rol.id})")
        await interaction.response.send_message(f"✅ Rol configurado: {rol.mention}\nLos usuarios con este rol ahora pueden usar el comando `/mi_tiempo`.")

    except Exception as e:
        print(f"❌ Error configurando rol de /mi_tiempo: {e}")
        await interaction.response.send_message("❌ Error al configurar el rol. Intenta de nuevo.")

async def send_auto_cancellation_notification(user_name: str, total_time: str, cancelled_by: str, pause_count: int):
    """Enviar notificación cuando un usuario es cancelado automáticamente por 3 pausas"""
    channel = bot.get_channel(CANCELLATION_NOTIFICATION_CHANNEL_ID)
    if channel:
        try:
            message = f"🚫 **CANCELACIÓN AUTOMÁTICA**\n**{user_name}** ha sido cancelado automáticamente por exceder el límite de pausas\n**Tiempo total perdido:** {total_time}\n**Pausas alcanzadas:** {pause_count}/3\n**Última pausa ejecutada por:** {cancelled_by}"
            await channel.send(message)
            print(f"✅ Notificación de cancelación automática enviada para {user_name}")
        except Exception as e:
            print(f"❌ Error enviando notificación de cancelación automática: {e}")
    else:
        print(f"❌ No se pudo encontrar el canal de cancelaciones con ID: {CANCELLATION_NOTIFICATION_CHANNEL_ID}")

async def send_cancellation_notification(user_name: str, cancelled_by: str, cancelled_time: str = ""):
    """Enviar notificación cuando un usuario es cancelado"""
    channel = bot.get_channel(CANCELLATION_NOTIFICATION_CHANNEL_ID)
    if channel:
        try:
            if cancelled_time:
                message = f"🗑️ El seguimiento de tiempo de **{user_name}** ha sido cancelado\n**Tiempo cancelado:** {cancelled_time}\n**Cancelado por:** {cancelled_by}"
            else:
                message = f"🗑️ El seguimiento de tiempo de **{user_name}** ha sido cancelado por {cancelled_by}"
            await channel.send(message)
            print(f"✅ Notificación de cancelación enviada para {user_name}")
        except Exception as e:
            print(f"❌ Error enviando notificación de cancelación: {e}")
    else:
        print(f"❌ No se pudo encontrar el canal de cancelaciones con ID: {CANCELLATION_NOTIFICATION_CHANNEL_ID}")

async def send_pause_notification(user_name: str, total_time: float, paused_by: str, session_time: str = "", pause_count: int = 0):
    """Enviar notificación cuando un usuario es pausado"""
    channel = bot.get_channel(PAUSE_NOTIFICATION_CHANNEL_ID)
    if channel:
        try:
            formatted_total_time = time_tracker.format_time_human(total_time)
            pause_text = f"pausa" if pause_count == 1 else f"pausas"
            if session_time and session_time != "0 Segundos":
                message = f"⏸️ El tiempo de **{user_name}** ha sido pausado\n**Tiempo de sesión pausado:** {session_time}\n**Tiempo total acumulado:** {formatted_total_time}\n**Pausado por:** {paused_by}\n📊 **{user_name}** lleva {pause_count} {pause_text}"
            else:
                message = f"⏸️ El tiempo de **{user_name}** ha sido pausado por {paused_by}\n**Tiempo total acumulado:** {formatted_total_time}\n📊 **{user_name}** lleva {pause_count} {pause_text}"
            await channel.send(message)
            print(f"✅ Notificación de pausa enviada para {user_name}")
        except Exception as e:
            print(f"❌ Error enviando notificación de pausa: {e}")
    else:
        print(f"❌ No se pudo encontrar el canal de pausas con ID: {PAUSE_NOTIFICATION_CHANNEL_ID}")

async def send_unpause_notification(user_name: str, total_time: float, unpaused_by: str, paused_duration: str = ""):
    """Enviar notificación cuando un usuario es despausado"""
    channel_id = config.get("notification_channels", {}).get("unpause")
    if channel_id:
        channel = bot.get_channel(channel_id)
        if channel:
            try:
                formatted_total_time = time_tracker.format_time_human(total_time)
                if paused_duration:
                    message = f"▶️ El tiempo de **{user_name}** ha sido despausado\n**Tiempo total acumulado:** {formatted_total_time}\n**Tiempo pausado:** {paused_duration}\n**Despausado por:** {unpaused_by}"
                else:
                    message = f"▶️ **{user_name}** ha sido despausado por {unpaused_by}. Tiempo acumulado: {formatted_total_time}"
                await channel.send(message)
                print(f"✅ Notificación de despausa enviada para {user_name}")
            except Exception as e:
                print(f"❌ Error enviando notificación de despausa: {e}")
        else:
            print(f"❌ No se pudo encontrar el canal de despausas con ID: {channel_id}")
    else:
        print("❌ Canal de despausas no configurado")

async def check_time_milestone(user_id: int, user_name: str):
    """Verificar si el usuario ha alcanzado milestones de tiempo y enviar notificaciones"""
    user_data = time_tracker.get_user_data(user_id)
    if not user_data:
        return

    # Verificar si el usuario está en el servidor
    guild = bot.guilds[0] if bot.guilds else None
    member = guild.get_member(user_id) if guild else None
    
    # Para usuarios externos (comandos de prefijo), asumir sin rol especial
    has_unlimited_role = False
    if member:
        has_unlimited_role = has_unlimited_time_role(member)
    else:
        # Usuario externo (comando de prefijo) - sin rol especial
        has_unlimited_role = False

    # Solo verificar si el usuario está activo o pausado (pero no completamente detenido)
    if not user_data.get('is_active', False):
        return

    # Calcular tiempo de la sesión actual
    if not user_data.get('last_start'):
        return

    session_start = datetime.fromisoformat(user_data['last_start'])

    # Si está pausado, calcular tiempo hasta la pausa
    if user_data.get('is_paused', False) and user_data.get('pause_start'):
        pause_start = datetime.fromisoformat(user_data['pause_start'])
        session_time = (pause_start - session_start).total_seconds()
    else:
        # Si está activo, calcular tiempo hasta ahora
        current_time = datetime.now()
        session_time = (current_time - session_start).total_seconds()

    # Solo proceder si la sesión actual ha alcanzado 1 hora
    if session_time < 3600:
        return

    total_time = time_tracker.get_total_time(user_id)
    print(f"Verificando milestone para {user_name}: sesión {session_time}s, total {total_time}s")
    print(f"  Estado: activo={user_data.get('is_active')}, pausado={user_data.get('is_paused')}")

    # Asegurar que existe el campo notified_milestones
    if 'notified_milestones' not in user_data:
        user_data['notified_milestones'] = []
        time_tracker.save_data()

    notified_milestones = user_data.get('notified_milestones', [])

    # Calcular cuántas horas totales tiene el usuario
    total_hours = int(total_time // 3600)
    hour_milestone = total_hours * 3600

    # Verificar si hay milestones perdidos (usuario tiene tiempo acumulado pero sin notificaciones)
    missing_milestones = []
    for h in range(1, total_hours + 1):
        milestone = h * 3600
        if milestone not in notified_milestones:
            missing_milestones.append((milestone, h))

    # Si hay milestones perdidos, notificar el más reciente
    if missing_milestones:
        milestone_to_notify, hours_to_notify = missing_milestones[-1]
        print(f"Detectado milestone perdido: {hours_to_notify} hora(s) para {user_name}")

        # Marcar TODOS los milestones perdidos como notificados
        for milestone, _ in missing_milestones:
            if milestone not in notified_milestones:
                notified_milestones.append(milestone)
        user_data['notified_milestones'] = notified_milestones
        time_tracker.save_data()

        # Detener el seguimiento después de completar 1 hora de sesión
        time_tracker.stop_tracking(user_id)

        # Enviar notificación
        channel = bot.get_channel(NOTIFICATION_CHANNEL_ID)
        if channel:
            try:
                formatted_time = time_tracker.format_time_human(total_time)

                if hours_to_notify == 1:
                    message = f"🎉 **{user_name}** ha completado 1 Hora! Tiempo acumulado: {formatted_time} "
                else:
                    message = f"🎉 **{user_name}** ha completado {hours_to_notify} Horas! Tiempo acumulado: {formatted_time} "

                await asyncio.wait_for(channel.send(message), timeout=10.0)
                print(f"✅ Notificación enviada: {user_name} completó {hours_to_notify} hora(s)")
                print(f"Seguimiento detenido automáticamente para {user_name}")
                return
            except asyncio.TimeoutError:
                print(f"⚠️ Timeout enviando notificación de milestone para {user_name}")
            except discord.HTTPException as e:
                print(f"❌ Error HTTP enviando notificación de milestone: {e}")
            except Exception as e:
                print(f"❌ Error enviando notificación: {e}")
        else:
            print(f"❌ No se pudo encontrar el canal con ID: {NOTIFICATION_CHANNEL_ID}")

    # Verificar si ya se notificó este milestone específico
    elif hour_milestone not in notified_milestones:
        print(f"Enviando notificación de {total_hours} Hora(s) para {user_name}...")

        # Marcar este milestone como notificado
        notified_milestones.append(hour_milestone)
        user_data['notified_milestones'] = notified_milestones
        time_tracker.save_data()

        # Detener seguimiento para usuarios sin rol especial, pausar para usuarios con rol especial
        if not has_unlimited_role:
            time_tracker.stop_tracking(user_id)
            print(f"Seguimiento detenido automáticamente para {user_name} (sin rol especial)")
        else:
            # Para usuarios con rol especial - detener seguimiento en todos los milestones
            time_tracker.stop_tracking(user_id)
            # Marcar como milestone completado para mostrar estado "Terminado"
            user_data = time_tracker.get_user_data(user_id)
            if user_data:
                user_data['milestone_completed'] = True
                time_tracker.save_data()
            print(f"Seguimiento detenido automáticamente para {user_name} (milestone {int(total_hours)} hora(s) completado - rol especial)")

        # Enviar notificación
        channel = bot.get_channel(NOTIFICATION_CHANNEL_ID)
        if channel:
            try:
                formatted_time = time_tracker.format_time_human(total_time)

                if total_hours == 1:
                    if not has_unlimited_role:
                        message = f"🎉 **{user_name}** ha completado 1 Hora! Tiempo acumulado: {formatted_time} "
                    else:
                        message = f"🎉 **{user_name}** ha completado 1 Hora! Tiempo acumulado: {formatted_time} "
                else:
                    message = f"🎉 **{user_name}** ha completado {total_hours} Horas! Tiempo acumulado: {formatted_time} "

                await asyncio.wait_for(channel.send(message), timeout=10.0)
                print(f"✅ Notificación enviada: {user_name} completó {total_hours} hora(s)")
            except asyncio.TimeoutError:
                print(f"⚠️ Timeout enviando notificación de milestone para {user_name}")
            except discord.HTTPException as e:
                print(f"❌ Error HTTP enviando notificación de milestone: {e}")
            except Exception as e:
                print(f"❌ Error enviando notificación: {e}")
        else:
            print(f"❌ No se pudo encontrar el canal con ID: {NOTIFICATION_CHANNEL_ID}")
    else:
        print(f"{user_name} ya fue notificado del milestone {total_hours} hora(s)")

async def check_missing_milestones():
    """Verificar y notificar milestones perdidos para todos los usuarios"""
    try:
        tracked_users = time_tracker.get_all_tracked_users()

        for user_id_str, data in tracked_users.items():
            user_id = int(user_id_str)
            user_name = data.get('name', f'Usuario {user_id}')
            total_time = time_tracker.get_total_time(user_id)

            # Verificar si el usuario está en el servidor
            guild = bot.guilds[0] if bot.guilds else None
            member = guild.get_member(user_id) if guild else None
            
            # Para usuarios externos (comandos de prefijo), continuar con verificación
            has_unlimited_role = False
            if member:
                has_unlimited_role = has_unlimited_time_role(member)
            else:
                # Usuario externo (comando de prefijo) - sin rol especial
                has_unlimited_role = False

            # Asegurar que existe el campo notified_milestones
            if 'notified_milestones' not in data:
                data['notified_milestones'] = []
                time_tracker.save_data()

            notified_milestones = data.get('notified_milestones', [])
            total_hours = int(total_time // 3600)

            # Verificar milestones perdidos
            missing_milestones = []
            for h in range(1, total_hours + 1):
                milestone = h * 3600
                if milestone not in notified_milestones:
                    missing_milestones.append((milestone, h))

            # Notificar milestone más alto perdido (solo una vez)
            if missing_milestones:
                milestone_to_notify, hours_to_notify = missing_milestones[-1]
                print(f"Detectado milestone perdido: {hours_to_notify} hora(s) para {user_name} (total: {total_time}s)")

                # Marcar todos los milestones perdidos como notificados
                for milestone, _ in missing_milestones:
                    if milestone not in notified_milestones:
                        notified_milestones.append(milestone)
                data['notified_milestones'] = notified_milestones
                time_tracker.save_data()

                print(f"Usuario {user_name}: {'con rol especial' if has_unlimited_role else 'sin rol especial'}")

                # Detener seguimiento para todos los usuarios en milestones
                if hours_to_notify >= 1:
                    time_tracker.stop_tracking(user_id)
                    # Marcar como milestone completado para usuarios con rol especial
                    if has_unlimited_role:
                        user_data = time_tracker.get_user_data(user_id)
                        if user_data:
                            user_data['milestone_completed'] = True
                            time_tracker.save_data()
                        print(f"Seguimiento detenido automáticamente para {user_name} (milestone {hours_to_notify} hora(s) completado - rol especial)")
                    else:
                        print(f"Seguimiento detenido automáticamente para {user_name} (sin rol especial)")

                # Enviar notificación
                channel = bot.get_channel(NOTIFICATION_CHANNEL_ID)
                if channel:
                    try:
                        formatted_time = time_tracker.format_time_human(total_time)

                        if hours_to_notify == 1:
                            message = f"🎉 **{user_name}** ha completado 1 Hora! Tiempo acumulado: {formatted_time} "
                        else:
                            message = f"🎉 **{user_name}** ha completado {hours_to_notify} Horas! Tiempo acumulado: {formatted_time} "

                        await asyncio.wait_for(channel.send(message), timeout=10.0)
                        print(f"✅ Notificación de milestone perdido enviada: {user_name} - {hours_to_notify} hora(s)")
                    except asyncio.TimeoutError:
                        print(f"⚠️ Timeout enviando notificación de milestone para {user_name}")
                    except discord.HTTPException as e:
                        print(f"❌ Error HTTP enviando notificación de milestone perdido: {e}")
                    except Exception as e:
                        print(f"❌ Error enviando notificación de milestone perdido: {e}")

                # Marcar que este usuario ya fue procesado en esta verificación para evitar duplicados
                data['last_milestone_check'] = total_time
                time_tracker.save_data()

    except Exception as e:
        print(f"❌ Error verificando milestones perdidos: {e}")



async def periodic_milestone_check():
    """Verificar milestones periódicamente para usuarios activos"""
    milestone_check_count = 0

    while True:
        try:
            await asyncio.sleep(5)  # Verificar cada 5 segundos
            milestone_check_count += 1

            # Verificar milestones perdidos cada 12 ciclos (cada minuto)
            if milestone_check_count % 12 == 1:
                await check_missing_milestones()

            # Verificar usuarios activos para sesiones de 1 hora
            tracked_users = time_tracker.get_all_tracked_users()
            for user_id_str, data in tracked_users.items():
                if data.get('is_active', False) and not data.get('is_paused', False):
                    user_id = int(user_id_str)
                    user_name = data.get('name', f'Usuario {user_id}')
                    await check_time_milestone(user_id, user_name)

        except Exception as e:
            print(f"Error en verificación periódica de milestones: {e}")
            await asyncio.sleep(10)

# Iniciar la verificación periódica después de definir la función
async def start_periodic_checks():
    """Iniciar la verificación periódica de milestones y Gold"""
    global milestone_check_task
    if milestone_check_task is None:
        milestone_check_task = bot.loop.create_task(periodic_milestone_check())
        print('✅ Task de verificación de milestones iniciado')



# Agregar la inicialización al final del archivo
@bot.event
async def on_connect():
    """Evento que se ejecuta cuando el bot se conecta"""
    await start_periodic_checks()

@bot.tree.command(name="saber_tiempo", description="Ver estadísticas detalladas de un usuario")
@discord.app_commands.describe(usuario="El usuario del que ver estadísticas")
@is_admin()
async def saber_tiempo_admin(interaction: discord.Interaction, usuario: discord.Member):
    user_data = time_tracker.get_user_data(usuario.id)

    if not user_data:
        await interaction.response.send_message(f"❌ No se encontraron datos para {usuario.mention}")
        return

    total_time = time_tracker.get_total_time(usuario.id)
    formatted_time = time_tracker.format_time_human(total_time)

    embed = discord.Embed(
        title=f"📊 Estadísticas de {usuario.display_name}",
        color=discord.Color.green(),
        timestamp=datetime.now()
    )

    embed.add_field(name="⏱️ Tiempo Total", value=formatted_time, inline=True)

    # Verificar si el usuario tiene rol especial
    has_special_role = has_unlimited_time_role(usuario)

    status = "🟢 Activo" if user_data.get('is_active', False) else "🔴 Inactivo"
    if user_data.get('is_paused', False):
        total_hours = total_time / 3600
        # Verificar si completó milestone y debe mostrar como "Terminado"
        if user_data.get("milestone_completed", False) or (has_special_role and total_hours >= 4.0) or (not has_special_role and total_hours >= 2.0):
            status = "✅ Terminado"
        else:
            status = "⏸️ Pausado"

    embed.add_field(name="📍 Estado", value=status, inline=True)

    # Mostrar tiempo pausado si está pausado
    if user_data.get('is_paused', False):
        paused_duration = time_tracker.get_paused_duration(usuario.id)
        formatted_paused_time = time_tracker.format_time_human(paused_duration) if paused_duration > 0 else "0 Segundos"
        embed.add_field(
            name=f"⏸️ Tiempo Pausado de {usuario.display_name}", 
            value=formatted_paused_time, 
            inline=False
        )

    # Mostrar contador de pausas
    pause_count = time_tracker.get_pause_count(usuario.id)
    if pause_count > 0:
        pause_text = "pausa" if pause_count == 1 else "pausas"
        embed.add_field(
            name="📊 Contador de Pausas", 
            value=f"{pause_count} {pause_text} de 3 máximo", 
            inline=True
        )

    embed.set_thumbnail(url=usuario.avatar.url if usuario.avatar else usuario.default_avatar.url)
    embed.set_footer(text="Estadísticas actualizadas")

    await interaction.response.send_message(embed=embed)





def check_mi_tiempo_permission():
    """Decorator para verificar si el usuario puede usar /mi_tiempo"""
    async def predicate(interaction: discord.Interaction) -> bool:
        try:
            if not hasattr(interaction, 'guild') or not interaction.guild:
                return False

            member = interaction.guild.get_member(interaction.user.id)
            if not member:
                return False

            # Verificar si tiene el rol autorizado para /mi_tiempo
            return can_use_mi_tiempo(member)

        except Exception as e:
            print(f"Error en verificación de permisos /mi_tiempo: {e}")
            return False

    return discord.app_commands.check(predicate)

@bot.tree.command(name="mi_tiempo", description="Ver tu propio tiempo acumulado")
@check_mi_tiempo_permission()
async def mi_tiempo(interaction: discord.Interaction):
    # El decorator ya verificó los permisos, por lo que este código es seguro ejecutar
    member = interaction.guild.get_member(interaction.user.id)

    user_data = time_tracker.get_user_data(interaction.user.id)

    if not user_data:
        await interaction.response.send_message("❌ No tienes tiempo registrado aún")
        return

    total_time = time_tracker.get_total_time(interaction.user.id)
    formatted_time = time_tracker.format_time_human(total_time)

    embed = discord.Embed(
        title=f"⏱️ Tu Tiempo Acumulado",
        color=discord.Color.from_rgb(255, 215, 0),
        timestamp=datetime.now()
    )

    # Usar formato humano detallado para /mi_tiempo
    formatted_time = time_tracker.format_time_human(total_time)
    embed.add_field(name="⏱️ Tiempo Total", value=formatted_time, inline=True)

    # Verificar si el usuario tiene rol especial (ya tenemos el member object)
    has_special_role = has_unlimited_time_role(member)

    status = "🟢 Activo" if user_data.get('is_active', False) else "🔴 Inactivo"
    if user_data.get('is_paused', False):
        total_hours = total_time / 3600
        # Verificar si completó milestone y debe mostrar como "Terminado"
        if user_data.get("milestone_completed", False) or (has_special_role and total_hours >= 4.0) or (not has_special_role and total_hours >= 2.0):
            status = "✅ Terminado"
        else:
            status = "⏸️ Pausado"

    embed.add_field(name="📍 Estado", value=status, inline=True)

    # Calcular y mostrar créditos
    credits = calculate_credits(total_time, has_special_role)
    if credits > 0:
        embed.add_field(name="💰 Créditos", value=f"{credits} créditos", inline=True)



    if user_data.get('last_start'):
        last_start = datetime.fromisoformat(user_data['last_start'])
        embed.add_field(
            name="🕐 Última Sesión Iniciada", 
            value=last_start.strftime("%d/%m/%Y %H:%M:%S"), 
            inline=False
        )

    embed.set_thumbnail(url=interaction.user.avatar.url if interaction.user.avatar else interaction.user.default_avatar.url)
    embed.set_footer(text="Consulta tu tiempo cuando quieras")

    await interaction.response.send_message(embed=embed)





# =================== COMANDOS DE PREFIJO ===================

@bot.command(name="iniciar")
@commands.has_permissions(administrator=True)
async def iniciar_prefix(ctx, usuario_nombre: str):
    """Comando de prefijo para iniciar tiempo: !iniciar usuario"""
    # Buscar usuario por nombre (sin importar si está en el servidor)
    user_id = None
    user_display_name = usuario_nombre
    found_member = None

    # Primero intentar buscar en el servidor actual
    if ctx.guild:
        # Buscar por nombre de usuario o display name
        member = discord.utils.find(
            lambda m: m.name.lower() == usuario_nombre.lower() or 
                     m.display_name.lower() == usuario_nombre.lower(),
            ctx.guild.members
        )

        if member:
            user_id = member.id
            user_display_name = member.display_name
            found_member = member

            # Verificar si es bot
            if member.bot:
                await ctx.send("❌ No se puede rastrear el tiempo de bots.")
                return

            # Verificar límites según el rol del usuario
            has_unlimited_role = has_unlimited_time_role(member)
            total_time = time_tracker.get_total_time(user_id)
            total_hours = total_time / 3600

            if not has_unlimited_role:
                if total_hours >= 1.0:
                    formatted_time = time_tracker.format_time_human(total_time)
                    await ctx.send(
                        f"❌ {member.mention} ya ha alcanzado el límite máximo de 1 hora (Tiempo actual: {formatted_time}). "
                        f"No se puede iniciar más seguimiento."
                    )
                    return
            else:
                if total_hours >= 4.0:
                    formatted_time = time_tracker.format_time_human(total_time)
                    await ctx.send(
                        f"❌ {member.mention} ya ha alcanzado el límite máximo de 4 horas (Tiempo actual: {formatted_time}). "
                        f"No se puede iniciar más seguimiento."
                    )
                    return

            # Verificar si el usuario tiene tiempo pausado
            user_data = time_tracker.get_user_data(user_id)
            if user_data and user_data.get('is_paused', False):
                await ctx.send(
                    f"⚠️ {member.mention} tiene tiempo pausado. Usa `!despausar {usuario_nombre}` para continuar el tiempo."
                )
                return

    # Si no se encontró en el servidor, crear un ID ficticio basado en el nombre
    if user_id is None:
        # Generar ID basado en hash del nombre para consistencia
        import hashlib
        user_id = int(hashlib.md5(usuario_nombre.lower().encode()).hexdigest()[:8], 16)
        user_display_name = usuario_nombre

    success = time_tracker.start_tracking(user_id, user_display_name)
    if success:
        # Marcar que este usuario es ficticio (no está en el servidor) para verificaciones futuras
        user_data = time_tracker.get_user_data(user_id)
        if user_data and not found_member:
            user_data['is_external_user'] = True
            time_tracker.save_data()
        
        await ctx.send(f"⏰ El tiempo de **{user_display_name}** ha sido iniciado por {ctx.author.mention}")
    else:
        await ctx.send(f"⚠️ El tiempo de **{user_display_name}** ya está activo")

@bot.command(name="sumar")
@commands.has_permissions(administrator=True)
async def sumar_prefix(ctx, usuario_nombre: str, minutos: int):
    """Comando de prefijo para sumar minutos: !sumar usuario minutos"""
    if minutos <= 0:
        await ctx.send("❌ La cantidad de minutos debe ser positiva")
        return

    # Buscar usuario por nombre
    user_id = None
    user_display_name = usuario_nombre

    # Primero intentar buscar en el servidor actual
    if ctx.guild:
        member = discord.utils.find(
            lambda m: m.name.lower() == usuario_nombre.lower() or 
                     m.display_name.lower() == usuario_nombre.lower(),
            ctx.guild.members
        )

        if member:
            user_id = member.id
            user_display_name = member.display_name

    # Si no se encontró en el servidor, crear un ID ficticio basado en el nombre
    if user_id is None:
        import hashlib
        user_id = int(hashlib.md5(usuario_nombre.lower().encode()).hexdigest()[:8], 16)
        user_display_name = usuario_nombre

    success = time_tracker.add_minutes(user_id, user_display_name, minutos)
    if success:
        total_time = time_tracker.get_total_time(user_id)
        formatted_time = time_tracker.format_time_human(total_time)
        await ctx.send(
            f"✅ Sumados {minutos} minutos a **{user_display_name}** por {ctx.author.mention}\n"
            f"⏱️ Tiempo total: {formatted_time}"
        )
        # Verificar milestone después de sumar tiempo
        await check_time_milestone(user_id, user_display_name)
    else:
        await ctx.send(f"❌ Error al sumar tiempo para **{user_display_name}**")

@bot.command(name="restar")
@commands.has_permissions(administrator=True)
async def restar_prefix(ctx, usuario_nombre: str, minutos: int):
    """Comando de prefijo para restar minutos: !restar usuario minutos"""
    if minutos <= 0:
        await ctx.send("❌ La cantidad de minutos debe ser positiva")
        return

    # Buscar usuario por nombre
    user_id = None
    user_display_name = usuario_nombre

    # Primero intentar buscar en el servidor actual
    if ctx.guild:
        member = discord.utils.find(
            lambda m: m.name.lower() == usuario_nombre.lower() or 
                     m.display_name.lower() == usuario_nombre.lower(),
            ctx.guild.members
        )

        if member:
            user_id = member.id
            user_display_name = member.display_name

    # Si no se encontró en el servidor, buscar en datos existentes
    if user_id is None:
        import hashlib
        potential_user_id = int(hashlib.md5(usuario_nombre.lower().encode()).hexdigest()[:8], 16)

        # Verificar si existe en los datos
        if time_tracker.get_user_data(potential_user_id):
            user_id = potential_user_id
            user_display_name = usuario_nombre
        else:
            await ctx.send(f"❌ No se encontraron datos para **{usuario_nombre}**")
            return

    success = time_tracker.subtract_minutes(user_id, minutos)
    if success:
        total_time = time_tracker.get_total_time(user_id)
        formatted_time = time_tracker.format_time_human(total_time)
        await ctx.send(
            f"➖ Restados {minutos} minutos de **{user_display_name}** por {ctx.author.mention}\n"
            f"⏱️ Tiempo total: {formatted_time}"
        )
    else:
        await ctx.send(f"❌ Error al restar tiempo para **{user_display_name}**")

@bot.command(name="cancelar")
@commands.has_permissions(administrator=True)
async def cancelar_prefix(ctx, usuario_nombre: str):
    """Comando de prefijo para cancelar tiempo: !cancelar usuario"""
    # Buscar usuario por nombre
    user_id = None
    user_display_name = usuario_nombre

    # Primero intentar buscar en el servidor actual
    if ctx.guild:
        member = discord.utils.find(
            lambda m: m.name.lower() == usuario_nombre.lower() or 
                     m.display_name.lower() == usuario_nombre.lower(),
            ctx.guild.members
        )

        if member:
            user_id = member.id
            user_display_name = member.display_name

    # Si no se encontró en el servidor, buscar en datos existentes
    if user_id is None:
        import hashlib
        potential_user_id = int(hashlib.md5(usuario_nombre.lower().encode()).hexdigest()[:8], 16)

        # Verificar si existe en los datos
        if time_tracker.get_user_data(potential_user_id):
            user_id = potential_user_id
            user_display_name = usuario_nombre
        else:
            await ctx.send(f"❌ No se encontraron datos para **{usuario_nombre}**")
            return

    # Obtener el tiempo antes de cancelar
    total_time = time_tracker.get_total_time(user_id)
    user_data = time_tracker.get_user_data(user_id)

    if user_data:
        formatted_time = time_tracker.format_time_human(total_time)
        success = time_tracker.cancel_user_tracking(user_id)
        if success:
            await ctx.send(f"🗑️ El tiempo de **{user_display_name}** ha sido cancelado")
            # Enviar notificación al canal de cancelaciones con tiempo cancelado
            await send_cancellation_notification(user_display_name, ctx.author.mention, formatted_time)
        else:
            await ctx.send(f"❌ Error al cancelar el tiempo para **{user_display_name}**")
    else:
        await ctx.send(f"❌ No se encontró registro de tiempo para **{user_display_name}**")

@bot.command(name="despausar")
@commands.has_permissions(administrator=True)
async def despausar_prefix(ctx, usuario_nombre: str):
    """Comando de prefijo para despausar tiempo: !despausar usuario"""
    # Buscar usuario por nombre
    user_id = None
    user_display_name = usuario_nombre
    found_member = None

    # Primero intentar buscar en el servidor actual
    if ctx.guild:
        member = discord.utils.find(
            lambda m: m.name.lower() == usuario_nombre.lower() or 
                     m.display_name.lower() == usuario_nombre.lower(),
            ctx.guild.members
        )

        if member:
            user_id = member.id
            user_display_name = member.display_name
            found_member = member

    # Si no se encontró en el servidor, buscar en datos existentes
    if user_id is None:
        import hashlib
        potential_user_id = int(hashlib.md5(usuario_nombre.lower().encode()).hexdigest()[:8], 16)

        # Verificar si existe en los datos
        if time_tracker.get_user_data(potential_user_id):
            user_id = potential_user_id
            user_display_name = usuario_nombre
        else:
            await ctx.send(f"❌ No se encontraron datos para **{usuario_nombre}**")
            return

    # Obtener duración pausada antes de despausar
    paused_duration = time_tracker.get_paused_duration(user_id)

    success = time_tracker.resume_tracking(user_id)
    if success:
        # Obtener tiempo total después de despausar
        total_time = time_tracker.get_total_time(user_id)
        formatted_paused_duration = time_tracker.format_time_human(paused_duration) if paused_duration > 0 else "0 Segundos"

        # Respuesta del comando
        await ctx.send(
            f"▶️ El tiempo de **{user_display_name}** ha sido despausado\n"
            f"**Tiempo pausado:** {formatted_paused_duration}\n"
            f"**Despausado por:** {ctx.author.mention}"
        )

        # Enviar notificación de despausa al canal específico
        await send_unpause_notification(user_display_name, total_time, ctx.author.mention, formatted_paused_duration)
    else:
        await ctx.send(f"⚠️ No se puede despausar - **{user_display_name}** no tiene tiempo pausado")

# Manejo de errores para comandos de prefijo
@iniciar_prefix.error
@sumar_prefix.error
@restar_prefix.error
@cancelar_prefix.error
@despausar_prefix.error
async def prefix_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ No tienes permisos de administrador para usar este comando.")
    elif isinstance(error, commands.MissingRequiredArgument):
        if ctx.command.name == "iniciar":
            await ctx.send("❌ Uso correcto: `!iniciar usuario`")
        elif ctx.command.name == "sumar":
            await ctx.send("❌ Uso correcto: `!sumar usuario minutos`")
        elif ctx.command.name == "restar":
            await ctx.send("❌ Uso correcto: `!restar usuario minutos`")
        elif ctx.command.name == "cancelar":
            await ctx.send("❌ Uso correcto: `!cancelar usuario`")
        elif ctx.command.name == "despausar":
            await ctx.send("❌ Uso correcto: `!despausar usuario`")
    elif isinstance(error, commands.BadArgument):
        if ctx.command.name in ["sumar", "restar"]:
            await ctx.send("❌ Los minutos deben ser un número válido.")
        else:
            await ctx.send("❌ Argumentos inválidos. Verifica el formato del comando.")
    else:
        await ctx.send("❌ Error inesperado. Intenta de nuevo.")
        print(f"Error en comando {ctx.command.name}: {error}")

# =================== COMANDOS ANTI AUSENTE ===================

def get_discord_token():
    """Obtener token de Discord de forma segura desde config.json o variables de entorno"""
    # Intentar obtener desde config.json primero
    if config and config.get('discord_bot_token'):
        token = config.get('discord_bot_token')
        if token and isinstance(token, str) and token.strip():
            print("✅ Token cargado desde config.json")
            return token.strip()

    # Si no está en config.json, intentar desde variables de entorno
    env_token = os.getenv('DISCORD_BOT_TOKEN')
    if env_token and isinstance(env_token, str) and env_token.strip():
        print("✅ Token cargado desde variables de entorno")
        return env_token.strip()

    # Si no se encuentra en ningún lado
    print("❌ Error: No se encontró el token de Discord")
    print("┌─ Configura tu token de Discord de una de estas formas:")
    print("│")
    print("│ OPCIÓN 1 (Recomendado): En config.json")
    print("│ Edita config.json y cambia:")
    print('│ "discord_bot_token": "tu_token_aqui"')
    print("│")
    print("│ OPCIÓN 2: Variable de entorno")
    print("│ export DISCORD_BOT_TOKEN='tu_token_aqui'")
    print("└─")
    return None

# Manejo global de errores para el bot
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    try:
        # Información para debugging
        command_name = interaction.command.name if interaction.command else 'desconocido'
        print(f"Error en comando /{command_name}: {type(error).__name__}")

        # Verificar si la interacción ya expiró antes de intentar responder
        if isinstance(error, discord.app_commands.CommandInvokeError):
            original_error = error.original if hasattr(error, 'original') else error

            # Si es un error de interacción expirada, no intentar responder
            if isinstance(original_error, discord.NotFound) and "10062" in str(original_error):
                print(f"⚠️ Interacción /{command_name} expirada (10062) - no respondiendo")
                return
            elif "Unknown interaction" in str(original_error):
                print(f"⚠️ Interacción /{command_name} desconocida - no respondiendo")
                return

        # Determinar mensaje de error apropiado
        if isinstance(error, discord.app_commands.CheckFailure):
            error_msg = "❌ No tienes permisos para usar este comando."
        elif isinstance(error, discord.app_commands.CommandInvokeError):
            error_msg = "❌ Error interno del comando. El administrador ha sido notificado."
        elif isinstance(error, discord.app_commands.TransformerError):
            error_msg = "❌ Error en los parámetros. Verifica los valores ingresados."
        elif isinstance(error, discord.app_commands.CommandOnCooldown):
            error_msg = f"⏰ Comando en cooldown. Intenta de nuevo en {error.retry_after:.1f}s"
        else:
            error_msg = "❌ Error inesperado. Intenta de nuevo."

        # Intentar responder de forma muy segura
        try:
            # Solo intentar responder si la interacción no está completa
            if not interaction.response.is_done():
                await asyncio.wait_for(
                    interaction.response.send_message(error_msg, ephemeral=True),
                    timeout=2.0  # Timeout de 2 segundos
                )
            else:
                await asyncio.wait_for(
                    interaction.followup.send(error_msg, ephemeral=True),
                    timeout=2.0
                )
        except asyncio.TimeoutError:
            print(f"⚠️ Timeout respondiendo a error en /{command_name}")
        except discord.NotFound:
            print(f"⚠️ Interacción /{command_name} no encontrada al responder error")
        except discord.HTTPException as e:
            if "10062" not in str(e):  # No login str(e):  # No logear errores de interacción expirada
                print(f"⚠️ Error HTTP respondiendo a /{command_name}: {e}")
        except Exception as e:
            print(f"⚠️ Error inesperado respondiendo a /{command_name}: {e}")

    except Exception as e:
        print(f"❌ Error crítico en manejo global de errores: {e}")

# Manejo específico de errores para comandos con @is_admin()
@iniciar_tiempo.error
@pausar_tiempo.error
@despausar_tiempo.error
@sumar_minutos.error
@restar_minutos.error
@ver_tiempos.error
@reiniciar_tiempo.error
@reiniciar_todos_tiempos.error
@cancelar_tiempo.error
@configurar_canal_tiempos.error
@configurar_canal_pausas.error
@configurar_canal_despausados.error
@saber_tiempo_admin.error
async def admin_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    # Solo manejar errores de permisos específicamente, dejar que el manejo global se encargue del resto
    if isinstance(error, discord.app_commands.CheckFailure):
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ No tienes permisos de administrador para usar este comando.", 
                    ephemeral=True
                )
        except discord.NotFound:
            pass  # Interacción expirada, ignorar
        except Exception:
            pass  # Cualquier otro error, ignorar para evitar loops
    # Para otros errores, dejar que el manejo global se encargue

#Agrego manejador de error para el comando mi_tiempo
@mi_tiempo.error
async def mi_tiempo_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    if isinstance(error, discord.app_commands.CheckFailure):
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ No tienes permisos para usar este comando.", 
                    ephemeral=True
                )
        except discord.NotFound:
            pass  # Interacción expirada, ignorar
        except Exception:
            pass  # Cualquier otro error, ignorar para evitar loops
    # Para otros errores, dejar que el manejo global se encargue



if __name__ == "__main__":
    print("🤖 Iniciando Discord Time Tracker Bot...")
    print("📋 Cargando configuración...")

    # Obtener token de Discord
    token = get_discord_token()
    if not token:
        exit(1)

    print("🔗 Conectando a Discord...")
    try:
        bot.run(token)
    except discord.LoginFailure:
        print("❌ Error: Token de Discord inválido")
        print("   Verifica que el token sea correcto en config.json")
        print("   O en las variables de entorno si usas esa opción")
    except KeyboardInterrupt:
        print("🛑 Bot detenido por el usuario")
    except Exception as e:
        print(f"❌ Error al iniciar el bot: {e}")
        print("   Revisa la configuración y vuelve a intentar")