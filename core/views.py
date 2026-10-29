from django.shortcuts import render,get_object_or_404
from .models import Categoria, Cancion, Servicio, Grupo, Perfil, Instrumento, RepertorioServicio
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q, Count
from datetime import date, time as datetime_time
from django.utils.safestring import mark_safe
import re
import logging
from django.contrib.auth import authenticate, login
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.shortcuts import render, redirect
from django.contrib.auth import logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
import json
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether


logger = logging.getLogger('emaus.trazabilidad')


def home(request):
    logger.info('HOME_REQUEST method=%s path=%s ip=%s', request.method, request.path, request.META.get('REMOTE_ADDR'))
    if request.method == 'POST':

        username = request.POST.get('username')
        password = request.POST.get('password')

        logger.info('LOGIN_ATTEMPT username=%r', username)
        user = authenticate(
            request,
            username=username,
            password=password
        )

        if user is not None:
            logger.info('LOGIN_AUTHENTICATED username=%s active=%s staff=%s superuser=%s', user.get_username(), user.is_active, user.is_staff, user.is_superuser)
            # Verificar si está activo
            if user.is_active:

                login(
                    request,
                    user
                )

                logger.info('LOGIN_SUCCESS username=%s session_key_present=%s', user.get_username(), bool(request.session.session_key))
                if not (user.is_staff or user.is_superuser):
                    perfil = getattr(user, 'perfil', None)
                    if perfil and perfil.debe_cambiar_password:
                        return redirect('primer_cambio_password')
                return redirect('loginin')

            return render(
                request,
                'index.html',
                {
                    'error':'Usuario deshabilitado'
                }
            )

        return render(
            request,
            'index.html',
            {
                'error':'Usuario o contraseña incorrecta'
            }
        )

    return render(
        request,
        'index.html'
    )

def contact(request):
    return render(request, 'contact.html')

def loginin(request):
    user = request.user
    logger.info('LOGININ_REQUEST authenticated=%s username=%s staff=%s superuser=%s active=%s session_key_present=%s',
        user.is_authenticated, user.get_username() if user.is_authenticated else 'anonymous',
        getattr(user, 'is_staff', False), getattr(user, 'is_superuser', False),
        getattr(user, 'is_active', False), bool(request.session.session_key))
    response = render(request, 'loginin.html')
    logger.info('LOGININ_RESPONSE status=%s content_type=%s', response.status_code, response.get('Content-Type'))
    return response


@csrf_exempt
def trazabilidad_preloader(request):
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)
    try:
        data = json.loads(request.body.decode('utf-8') or '{}')
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({'ok': False}, status=400)
    user = request.user
    logger.warning('BROWSER_PRELOADER event=%s detail=%r path=%s readyState=%s jquery=%s preloaderFound=%s user=%s authenticated=%s staff=%s superuser=%s ua=%r',
        str(data.get('event', 'unknown'))[:80], str(data.get('detail', ''))[:300],
        str(data.get('path', ''))[:150], str(data.get('readyState', ''))[:30],
        str(data.get('jquery', ''))[:30], str(data.get('preloaderFound', ''))[:10],
        user.get_username() if user.is_authenticated else 'anonymous', user.is_authenticated,
        getattr(user, 'is_staff', False), getattr(user, 'is_superuser', False),
        request.META.get('HTTP_USER_AGENT', '')[:180])
    return JsonResponse({'ok': True})


@login_required(login_url='home')
def primer_cambio_password(request):
    user = request.user
    if user.is_staff or user.is_superuser:
        return redirect('loginin')
    perfil = getattr(user, 'perfil', None)
    if not perfil or not perfil.debe_cambiar_password:
        return redirect('loginin')
    error = ''
    if request.method == 'POST':
        nueva = request.POST.get('password_nueva', '')
        confirmacion = request.POST.get('password_confirmacion', '')
        if len(nueva) < 8:
            error = 'La contraseña debe tener al menos 8 caracteres.'
        elif nueva != confirmacion:
            error = 'Las contraseñas no coinciden. Vuelve a escribirlas.'
        elif not any(ch.isalpha() for ch in nueva) or not any(ch.isdigit() for ch in nueva):
            error = 'Usa una combinación de letras y números para mayor seguridad.'
        else:
            user.set_password(nueva)
            user.save(update_fields=['password'])
            perfil.debe_cambiar_password = False
            perfil.save(update_fields=['debe_cambiar_password'])
            update_session_auth_hash(request, user)
            messages.success(request, 'Tu contraseña quedó actualizada. ¡Bienvenido!')
            return redirect('loginin')
    return render(request, 'primer_cambio_password.html', {'error': error})


@login_required(login_url='home')
def cambiar_password(request):
    error = ''
    if request.method == 'POST':
        password_actual = request.POST.get('password_actual', '')
        password_nueva = request.POST.get('password_nueva', '')
        password_confirmacion = request.POST.get('password_confirmacion', '')
        if not request.user.check_password(password_actual):
            error = 'La contraseña actual es incorrecta.'
        elif len(password_nueva) < 8:
            error = 'La nueva contraseña debe tener al menos 8 caracteres.'
        elif password_nueva != password_confirmacion:
            error = 'La nueva contraseña y su confirmación no coinciden.'
        elif password_actual == password_nueva:
            error = 'La nueva contraseña debe ser diferente de la actual.'
        else:
            request.user.set_password(password_nueva)
            request.user.save(update_fields=['password'])
            update_session_auth_hash(request, request.user)
            messages.success(request, 'Tu contraseña fue actualizada correctamente.')
            return redirect('loginin')
    return render(request, 'cambiar_password.html', {'error': error})



def calendario(request):
    """Muestra los servicios y los cumpleaños de los servidores activos."""
    servicios = [
        {
            'id': servicio.pk,
            'titulo': servicio.titulo,
            'grupo': servicio.grupo.nombre,
            'fecha': servicio.fecha.isoformat(),
            'hora_inicio': servicio.hora_inicio.strftime('%H:%M'),
            'hora_fin': servicio.hora_fin.strftime('%H:%M') if servicio.hora_fin else '',
            'lugar': servicio.lugar,
            'observaciones': servicio.observaciones,
            'tipo_grupo': servicio.grupo.tipo,
            'estado': servicio.estado,
        }
        for servicio in Servicio.objects.filter(
            activo=True,
            grupo__activo=True
        ).select_related('grupo').order_by('fecha', 'hora_inicio')
    ]

    cumpleanos = [
        {
            'nombre': perfil.nombres,
            'dia_mes': perfil.fecha_nacimiento.strftime('%m-%d'),
        }
        for perfil in Perfil.objects.filter(
            usuario__is_active=True,
            fecha_nacimiento__isnull=False,
        ).order_by('nombres')
    ]

    return render(request, 'calendario.html', {
        'servicios': servicios,
        'cumpleanos': cumpleanos,
    })



@staff_member_required(login_url='home')
def gestion_servicios(request):
    """Lista los servicios y permite crear, editar y eliminar servicios."""
    valores_formulario = {}
    abrir_modal = False
    modo_edicion = False
    servicio_id_form = ''

    hoy = date.today()
    if request.method == 'POST':
        mes_solicitado = request.POST.get('mes', '').strip()
        anio_solicitado = request.POST.get('anio', '').strip()
    else:
        mes_solicitado = request.GET.get('mes', '').strip()
        anio_solicitado = request.GET.get('anio', '').strip()

    try:
        mes_numero = int(mes_solicitado)
        anio_numero = int(anio_solicitado)
        if not 1 <= mes_numero <= 12 or not 1900 <= anio_numero <= 2200:
            raise ValueError
        mes_seleccionado_fecha = date(anio_numero, mes_numero, 1)
    except (ValueError, TypeError):
        mes_seleccionado_fecha = hoy.replace(day=1)

    mes_seleccionado = f'{mes_seleccionado_fecha.month:02d}'
    anio_seleccionado = str(mes_seleccionado_fecha.year)

    if request.method == 'POST':
        accion = request.POST.get('accion', '')

        if accion == 'eliminar_servicio':
            servicio = get_object_or_404(Servicio, pk=request.POST.get('servicio_id'))
            titulo_eliminado = servicio.titulo
            servicio.delete()
            messages.success(request, f'El servicio «{titulo_eliminado}» fue eliminado.')
            return redirect("/servicios/?mes=" + mes_seleccionado + "&anio=" + anio_seleccionado)

        if accion in ('crear_servicio', 'editar_servicio'):
            abrir_modal = True
            modo_edicion = accion == 'editar_servicio'
            servicio_id_form = request.POST.get('servicio_id', '').strip() if modo_edicion else ''
            servicio_editar = get_object_or_404(Servicio, pk=servicio_id_form) if modo_edicion else None

            campos = (
                'titulo', 'grupo_id', 'fecha', 'hora_inicio',
                'hora_fin', 'lugar', 'observaciones', 'estado',
            )
            valores_formulario = {
                campo: request.POST.get(campo, '').strip()
                for campo in campos
            }

            titulo = valores_formulario['titulo']
            grupo = Grupo.objects.filter(
                pk=valores_formulario['grupo_id'],
                activo=True,
            ).first()
            fecha_texto = valores_formulario['fecha']
            hora_inicio_texto = valores_formulario['hora_inicio']
            hora_fin_texto = valores_formulario['hora_fin']
            lugar = valores_formulario['lugar']
            observaciones = valores_formulario['observaciones']
            estado = valores_formulario['estado'] or Servicio.ESTADO_PROGRAMADO

            errores = []
            if not titulo:
                errores.append('El nombre del servicio es obligatorio.')
            elif len(titulo) > 150:
                errores.append('El nombre del servicio no puede superar 150 caracteres.')
            if not grupo:
                errores.append('Selecciona un grupo responsable activo.')

            fecha_servicio = None
            try:
                fecha_servicio = date.fromisoformat(fecha_texto)
            except (ValueError, TypeError):
                errores.append('Selecciona una fecha válida.')

            hora_inicio = None
            try:
                hora_inicio = datetime_time.fromisoformat(hora_inicio_texto)
            except (ValueError, TypeError):
                errores.append('La hora de inicio es obligatoria y debe ser válida.')

            hora_fin = None
            if hora_fin_texto:
                try:
                    hora_fin = datetime_time.fromisoformat(hora_fin_texto)
                except (ValueError, TypeError):
                    errores.append('La hora de finalización no es válida.')

            if hora_inicio and hora_fin and hora_fin <= hora_inicio:
                errores.append('La hora de finalización debe ser posterior a la hora de inicio.')
            if estado not in dict(Servicio.ESTADOS):
                errores.append('Selecciona un estado válido.')
            if len(lugar) > 200:
                errores.append('El lugar no puede superar 200 caracteres.')

            if errores:
                for error in errores:
                    messages.error(request, error)
            else:
                if modo_edicion:
                    servicio = servicio_editar
                    servicio.titulo = titulo
                    servicio.grupo = grupo
                    servicio.fecha = fecha_servicio
                    servicio.hora_inicio = hora_inicio
                    servicio.hora_fin = hora_fin
                    servicio.lugar = lugar
                    servicio.observaciones = observaciones
                    servicio.estado = estado
                    # Mantener visible el servicio en el calendario, que usa el campo heredado activo.
                    servicio.activo = True
                    servicio.save()
                    messages.success(request, f'El servicio «{servicio.titulo}» fue actualizado.')
                else:
                    servicio = Servicio.objects.create(
                        titulo=titulo,
                        grupo=grupo,
                        fecha=fecha_servicio,
                        hora_inicio=hora_inicio,
                        hora_fin=hora_fin,
                        lugar=lugar,
                        observaciones=observaciones,
                        estado=estado,
                        activo=True,
                    )
                    messages.success(
                        request,
                        f'Servicio «{servicio.titulo}» creado correctamente con el ID #{servicio.pk}.'
                    )
                return redirect("/servicios/?mes=" + mes_seleccionado + "&anio=" + anio_seleccionado)

    elif request.method == 'GET' and request.GET.get('editar'):
        servicio_editar = get_object_or_404(
            Servicio.objects.select_related('grupo'),
            pk=request.GET.get('editar'),
        )
        abrir_modal = True
        modo_edicion = True
        servicio_id_form = str(servicio_editar.pk)
        valores_formulario = {
            'titulo': servicio_editar.titulo,
            'grupo_id': str(servicio_editar.grupo_id),
            'fecha': servicio_editar.fecha.isoformat(),
            'hora_inicio': servicio_editar.hora_inicio.strftime('%H:%M') if servicio_editar.hora_inicio else '',
            'hora_fin': servicio_editar.hora_fin.strftime('%H:%M') if servicio_editar.hora_fin else '',
            'lugar': servicio_editar.lugar or '',
            'observaciones': servicio_editar.observaciones or '',
            'estado': servicio_editar.estado,
        }

    # El listado se filtra por mes y año seleccionados; los contadores siempre usan el año actual.
    servicios = Servicio.objects.select_related('grupo').filter(
        fecha__year=mes_seleccionado_fecha.year,
        fecha__month=mes_seleccionado_fecha.month,
    ).order_by('-fecha', '-hora_inicio', '-pk')

    servicios_anio = Servicio.objects.filter(fecha__year=hoy.year)
    totales_estado = {
        estado: servicios_anio.filter(estado=estado).count()
        for estado, etiqueta in Servicio.ESTADOS
    }

    grupos = list(Grupo.objects.filter(activo=True).order_by('nombre'))
    grupo_seleccionado = valores_formulario.get('grupo_id', '')
    for grupo in grupos:
        grupo.form_selected = str(grupo.pk) == grupo_seleccionado

    nombres_meses = [
        'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
        'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre',
    ]
    meses_disponibles = [
        {'valor': f'{numero:02d}', 'etiqueta': nombre.capitalize()}
        for numero, nombre in enumerate(nombres_meses, start=1)
    ]

    # Solo años con servicios, los años cercanos y el año seleccionado aparecen en el combo.
    anios_opciones = set(range(hoy.year - 5, hoy.year + 6))
    anios_opciones.update(
        fecha_anio.year for fecha_anio in Servicio.objects.dates('fecha', 'year', order='ASC')
    )
    anios_opciones.add(mes_seleccionado_fecha.year)
    anios_disponibles = [str(anio) for anio in sorted(anios_opciones, reverse=True)]

    mes_label = f'{nombres_meses[mes_seleccionado_fecha.month - 1].capitalize()} de {mes_seleccionado_fecha.year}'
    fecha_formulario_default = hoy.isoformat() if mes_seleccionado_fecha.year == hoy.year and mes_seleccionado_fecha.month == hoy.month else mes_seleccionado_fecha.isoformat()

    return render(request, 'servicios.html', {
        'servicios': servicios,
        'grupos': grupos,
        'total_programados': totales_estado[Servicio.ESTADO_PROGRAMADO],
        'total_en_ejecucion': totales_estado[Servicio.ESTADO_EN_EJECUCION],
        'total_terminados': totales_estado[Servicio.ESTADO_TERMINADO],
        'total_servicios': servicios_anio.count(),
        'anio_actual': hoy.year,
        'estados_servicio': Servicio.ESTADOS,
        'fecha_hoy': fecha_formulario_default,
        'valores_formulario': valores_formulario,
        'abrir_modal': abrir_modal,
        'modo_edicion': modo_edicion,
        'servicio_id_form': servicio_id_form,
        'meses_disponibles': meses_disponibles,
        'mes_seleccionado': mes_seleccionado,
        'anios_disponibles': anios_disponibles,
        'anio_seleccionado': anio_seleccionado,
        'mes_label': mes_label,
    })



@staff_member_required(login_url='home')
def exportar_servicios_pdf(request):
    """Exporta el calendario mensual de servicios con la identidad visual de Emaús."""
    from django.contrib.staticfiles import finders
    from svglib.svglib import svg2rlg
    from reportlab.graphics import renderPDF
    from reportlab.lib.pagesizes import A4
    from xml.sax.saxutils import escape

    hoy = date.today()
    try:
        mes = int(request.GET.get('mes', hoy.month))
        anio = int(request.GET.get('anio', hoy.year))
        if not 1 <= mes <= 12 or not 1900 <= anio <= 2200:
            raise ValueError
    except (ValueError, TypeError):
        mes, anio = hoy.month, hoy.year

    meses_es = [
        'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
        'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre',
    ]
    dias_es = [
        'lunes', 'martes', 'miércoles', 'jueves',
        'viernes', 'sábado', 'domingo',
    ]
    nombre_mes = meses_es[mes - 1]
    servicios_mes = list(
        Servicio.objects.select_related('grupo', 'grupo__lider')
        .filter(fecha__year=anio, fecha__month=mes)
        .order_by('fecha', 'hora_inicio', 'titulo')
    )

    buffer = BytesIO()
    ancho, alto = A4
    margen_lateral = 15 * mm
    ancho_util = ancho - margen_lateral * 2
    alto_cabecera = 58 * mm
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=margen_lateral,
        leftMargin=margen_lateral,
        topMargin=63 * mm,
        bottomMargin=19 * mm,
        title=f'Calendario de servicios - {nombre_mes.capitalize()} {anio}',
        author='Fundación de Fieles Caminantes de Emaús - Cuenca',
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name='CalendarioCell',
        parent=styles['BodyText'],
        fontName='Helvetica',
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor('#252329'),
        spaceAfter=0,
        wordWrap='CJK',
    ))
    styles.add(ParagraphStyle(
        name='CalendarioCellCenter',
        parent=styles['CalendarioCell'],
        alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        name='CalendarioCellBold',
        parent=styles['CalendarioCell'],
        fontName='Helvetica-Bold',
    ))
    styles.add(ParagraphStyle(
        name='CalendarioHeaderCell',
        parent=styles['BodyText'],
        fontName='Helvetica-Bold',
        fontSize=7.5,
        leading=9,
        textColor=colors.white,
        alignment=TA_LEFT,
    ))

    encabezados = [
        '#', 'FECHA', 'DÍA', 'SERVICIO / HORARIO',
        'RESPONSABLE', 'LÍDER DEL GRUPO', 'IGLESIA / LUGAR',
    ]
    filas = [[Paragraph(escape(texto), styles['CalendarioHeaderCell']) for texto in encabezados]]

    for numero, servicio in enumerate(servicios_mes, start=1):
        dia_semana = dias_es[servicio.fecha.weekday()].capitalize()
        fecha_texto = f'{servicio.fecha.day} de {meses_es[servicio.fecha.month - 1]}'
        horario = servicio.hora_inicio.strftime('%H:%M')
        if servicio.hora_fin:
            horario += '–' + servicio.hora_fin.strftime('%H:%M')
        servicio_html = (
            f'<b>{escape(servicio.titulo)}</b><br/>'
            f'<font size="7" color="#626262">{escape(horario)}</font>'
        )
        nombre_lider = servicio.grupo.lider.nombres if servicio.grupo.lider_id else 'Sin líder asignado'
        lugar = servicio.lugar.strip() if servicio.lugar else '—'
        filas.append([
            Paragraph(str(numero), styles['CalendarioCellCenter']),
            Paragraph(escape(fecha_texto), styles['CalendarioCell']),
            Paragraph(escape(dia_semana), styles['CalendarioCell']),
            Paragraph(servicio_html, styles['CalendarioCell']),
            Paragraph(escape(servicio.grupo.nombre), styles['CalendarioCellBold']),
            Paragraph(escape(nombre_lider), styles['CalendarioCell']),
            Paragraph(escape(lugar), styles['CalendarioCell']),
        ])

    if not servicios_mes:
        filas.append([
            Paragraph('—', styles['CalendarioCellCenter']),
            Paragraph('No hay servicios registrados para este mes.', styles['CalendarioCell']),
            Paragraph('', styles['CalendarioCell']),
            Paragraph('', styles['CalendarioCell']),
            Paragraph('', styles['CalendarioCell']),
            Paragraph('', styles['CalendarioCell']),
            Paragraph('', styles['CalendarioCell']),
        ])

    anchuras = [
        7 * mm, 27 * mm, 18 * mm, 39 * mm, 25 * mm, 32 * mm,
        ancho_util - (7 + 27 + 18 + 39 + 25 + 32) * mm,
    ]
    tabla = Table(filas, colWidths=anchuras, repeatRows=1, hAlign='LEFT')
    tabla.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#bd0026')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#b8b8b8')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1),
         [colors.HexColor('#f8e9ed'), colors.white]),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
    ]))
    story = [tabla]

    def dibujar_cabecera_pie(canvas, documento):
        canvas.saveState()
        negro = colors.HexColor('#000000')

        # Cabecera blanca, sin franjas de color, para imprimir limpiamente.
        canvas.setFillColor(colors.white)
        canvas.rect(0, alto - alto_cabecera, ancho, alto_cabecera, fill=1, stroke=0)

        # Logo centrado en una zona propia; el texto institucional queda debajo y sin solaparse.
        logo_path = finders.find('images/logomio_negro.svg')
        if logo_path:
            try:
                logo = svg2rlg(logo_path)
                if logo and logo.width and logo.height:
                    escala = min((42 * mm) / logo.width, (13 * mm) / logo.height)
                    x_logo = (ancho - logo.width * escala) / 2
                    y_logo = alto - 7 * mm - logo.height * escala
                    canvas.saveState()
                    canvas.translate(x_logo, y_logo)
                    canvas.scale(escala, escala)
                    renderPDF.draw(logo, canvas, 0, 0)
                    canvas.restoreState()
            except Exception:
                pass

        canvas.setFillColor(negro)
        canvas.setFont('Helvetica', 9)
        canvas.drawCentredString(
            ancho / 2, alto - 29 * mm,
            'Fundación de Fieles Caminantes de Emaús — Cuenca'
        )
        canvas.setFont('Helvetica-Bold', 12)
        canvas.drawCentredString(ancho / 2, alto - 36 * mm, 'Ministerio de Música')
        canvas.setFont('Helvetica-Bold', 15)
        canvas.drawCentredString(
            ancho / 2, alto - 48 * mm,
            f'CALENDARIO DE SERVICIOS — {nombre_mes.upper()} {anio}'
        )

        # Pie sobrio con acento rojo, sin sección de notas al final del documento.
        canvas.setStrokeColor(colors.HexColor('#777777'))
        canvas.setLineWidth(0.8)
        canvas.line(margen_lateral, 14 * mm, ancho - margen_lateral, 14 * mm)
        canvas.setFillColor(colors.HexColor('#555555'))
        canvas.setFont('Helvetica', 8.5)
        canvas.drawCentredString(ancho / 2, 8 * mm, 'Ministerio de Música — Emaús Cuenca')
        canvas.drawRightString(ancho - margen_lateral, 8 * mm, f'Página {documento.page}')
        canvas.restoreState()

    doc.build(story, onFirstPage=dibujar_cabecera_pie, onLaterPages=dibujar_cabecera_pie)
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = (
        f'attachment; filename="calendario_servicios_{anio}_{mes:02d}.pdf"'
    )
    buffer.close()
    return response


def servicios_visibles_para_usuario(user):
    """Staff puede gestionar todos los grupos; servidores solo su(s) grupo(s)."""
    base = Servicio.objects.filter(
        estado=Servicio.ESTADO_PROGRAMADO,
        fecha__gte=date.today(),
        activo=True,
        grupo__activo=True,
    )
    if user.is_staff or user.is_superuser:
        return base

    try:
        perfil = user.perfil
    except (Perfil.DoesNotExist, AttributeError):
        return base.none()

    # La asignación real se administra en Grupo.integrantes.
    # No confiar en Perfil.grupo, que puede estar desactualizado.
    return base.filter(
        grupo__tipo=Grupo.TIPO_PERMANENTE,
        grupo__integrantes=perfil,
    ).distinct()


@login_required(login_url='home')
def servicios_programados_para_cancion(request, cancion_id):
    """Lista solo los servicios programados próximos para añadir una canción al repertorio."""
    if request.method != 'GET':
        return JsonResponse({'ok': False, 'error': 'Método no permitido.'}, status=405)

    if not request.user.is_authenticated:
        return JsonResponse({'ok': False, 'error': 'Inicia sesión para consultar servicios.'}, status=401)

    cancion = get_object_or_404(Cancion, pk=cancion_id)
    servicios = list(
        servicios_visibles_para_usuario(request.user)
        .select_related('grupo')
        .prefetch_related('repertorio')
        .annotate(total_canciones=Count('repertorio'))
        .order_by('fecha', 'hora_inicio', 'pk')
    )

    ya_agregados = set(
        RepertorioServicio.objects.filter(
            cancion=cancion,
            servicio__in=servicios,
        ).values_list('servicio_id', flat=True)
    )
    dias_es = [
        'lunes', 'martes', 'miércoles', 'jueves',
        'viernes', 'sábado', 'domingo',
    ]
    meses_es = [
        'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
        'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre',
    ]

    resultados = []
    for servicio in servicios:
        resultados.append({
            'id': servicio.pk,
            'titulo': servicio.titulo,
            'fecha': servicio.fecha.isoformat(),
            'fecha_label': (
                f'{dias_es[servicio.fecha.weekday()].capitalize()} '
                f'{servicio.fecha.day} de {meses_es[servicio.fecha.month - 1]} de {servicio.fecha.year}'
            ),
            'hora_inicio': servicio.hora_inicio.strftime('%H:%M') if servicio.hora_inicio else '',
            'hora_fin': servicio.hora_fin.strftime('%H:%M') if servicio.hora_fin else '',
            'grupo': servicio.grupo.nombre,
            'lugar': servicio.lugar or 'Lugar por confirmar',
            'repertorio_count': servicio.total_canciones,
            'ya_agregada': servicio.pk in ya_agregados,
            'repertorio': [
                {
                    'id': entrada.pk,
                    'cancion_id': entrada.cancion_id,
                    'numero_snapshot': entrada.numero_snapshot,
                    'titulo_snapshot': entrada.titulo_snapshot,
                    'orden': entrada.orden,
                    'usa_capodastro': entrada.usa_capodastro,
                    'traste_capodastro': entrada.traste_capodastro,
                    'semitonos_transpuestos': entrada.semitonos_transpuestos,
                    'notacion_acordes': entrada.notacion_acordes,
                }
                for entrada in servicio.repertorio.all()
            ],
        })

    return JsonResponse({
        'ok': True,
        'cancion': {
            'id': cancion.pk,
            'numero': cancion.numero,
            'titulo': cancion.titulo,
            'usa_capodastro': cancion.usa_capodastro,
            'traste_capodastro': cancion.traste_capodastro,
        },
        'servicios': resultados,
    })


@login_required(login_url='home')
def agregar_cancion_a_servicio(request, cancion_id):
    """Guarda en un servicio una copia independiente de la versión visible de la canción."""
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Método no permitido.'}, status=405)

    try:
        data = json.loads(request.body.decode('utf-8') or '{}')
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({'ok': False, 'error': 'La solicitud no contiene datos válidos.'}, status=400)

    cancion = get_object_or_404(Cancion, pk=cancion_id)
    try:
        servicio_id = int(data.get('servicio_id'))
    except (ValueError, TypeError):
        return JsonResponse({'ok': False, 'error': 'Selecciona un servicio.'}, status=400)

    servicio = servicios_visibles_para_usuario(request.user).filter(
        pk=servicio_id,
    ).select_related('grupo').first()
    if not servicio:
        return JsonResponse({
            'ok': False,
            'error': 'Ese servicio ya no está programado o no es una fecha futura disponible.',
        }, status=400)

    letra_snapshot = data.get('letra_snapshot')
    if not isinstance(letra_snapshot, str) or not letra_snapshot.strip():
        return JsonResponse({
            'ok': False,
            'error': 'La canción no tiene letra o acordes para guardar.',
        }, status=400)

    try:
        semitonos = int(data.get('semitonos_transpuestos', 0))
    except (ValueError, TypeError):
        semitonos = 0
    if not -24 <= semitonos <= 24:
        return JsonResponse({'ok': False, 'error': 'La transposición indicada no es válida.'}, status=400)

    notacion = str(data.get('notacion_acordes', 'original'))
    if notacion not in dict(RepertorioServicio.NOTACIONES):
        notacion = RepertorioServicio.NOTACION_ORIGINAL

    usa_capodastro = data.get('usa_capodastro') is True
    traste_capodastro = None
    if usa_capodastro:
        try:
            traste_capodastro = int(data.get('traste_capodastro'))
        except (ValueError, TypeError):
            return JsonResponse({
                'ok': False,
                'error': 'Indica en qué traste se colocará el capodastro.',
            }, status=400)
        if not 1 <= traste_capodastro <= 12:
            return JsonResponse({
                'ok': False,
                'error': 'El traste del capodastro debe estar entre 1 y 12.',
            }, status=400)

    with transaction.atomic():
        orden_nuevo = servicio.repertorio.count() + 1
        entrada, creada = RepertorioServicio.objects.get_or_create(
            servicio=servicio,
            cancion=cancion,
            defaults={
                'numero_snapshot': cancion.numero,
                'titulo_snapshot': cancion.titulo,
                'letra_snapshot': letra_snapshot,
                'usa_capodastro': usa_capodastro,
                'traste_capodastro': traste_capodastro,
                'semitonos_transpuestos': semitonos,
                'notacion_acordes': notacion,
                'orden': orden_nuevo,
                'agregado_por': request.user,
            },
        )
        if not creada:
            # Una canción aparece una sola vez por servicio; al volver a guardarla,
            # se actualiza su copia dentro de ese repertorio, no la canción original.
            entrada.numero_snapshot = cancion.numero
            entrada.titulo_snapshot = cancion.titulo
            entrada.letra_snapshot = letra_snapshot
            entrada.usa_capodastro = usa_capodastro
            entrada.traste_capodastro = traste_capodastro
            entrada.semitonos_transpuestos = semitonos
            entrada.notacion_acordes = notacion
            entrada.agregado_por = request.user
            entrada.save(update_fields=[
                'numero_snapshot', 'titulo_snapshot', 'letra_snapshot',
                'usa_capodastro', 'traste_capodastro',
                'semitonos_transpuestos', 'notacion_acordes', 'agregado_por',
            ])

    return JsonResponse({
        'ok': True,
        'created': creada,
        'message': (
            'Canción agregada al repertorio del servicio.'
            if creada else
            'La canción ya estaba en este repertorio; se actualizó la versión guardada.'
        ),
        'repertorio_id': entrada.pk,
        'repertorio_count': servicio.repertorio.count(),
        'servicio': servicio.titulo,
        'fecha_servicio': servicio.fecha.strftime('%d/%m/%Y'),
        'cancion': entrada.titulo_snapshot,
        'usa_capodastro': entrada.usa_capodastro,
        'traste_capodastro': entrada.traste_capodastro,
        'semitonos_transpuestos': entrada.semitonos_transpuestos,
        'notacion_acordes': entrada.notacion_acordes,
    })



def buscar_canciones(request):
    """Busca coincidencias en todo el cancionero para el buscador lateral."""
    if request.method != 'GET':
        return JsonResponse({'ok': False, 'error': 'Método no permitido.'}, status=405)

    termino = request.GET.get('q', '').strip()[:100]
    if len(termino) < 2:
        return JsonResponse({'ok': True, 'results': []})

    coincidencias = Q(titulo__icontains=termino) | Q(letra__icontains=termino) | Q(categoria__nombre__icontains=termino)
    if termino.isdigit():
        coincidencias |= Q(numero=int(termino))

    canciones = Cancion.objects.select_related('categoria').filter(
        coincidencias
    ).order_by('numero', 'titulo')[:20]

    resultados = []
    for cancion in canciones:
        texto = (cancion.letra or '').replace('\r', ' ').replace('\n', ' ').strip()
        resultados.append({
            'id': cancion.pk,
            'numero': cancion.numero,
            'titulo': cancion.titulo,
            'categoria': cancion.categoria.nombre,
            'preview': texto[:140] + ('…' if len(texto) > 140 else ''),
        })

    return JsonResponse({'ok': True, 'results': resultados})


def detalle_cancion(request, id):
    """Devuelve los datos de una canción para mostrarla en el popup del buscador."""
    if request.method != 'GET':
        return JsonResponse({'ok': False, 'error': 'Método no permitido.'}, status=405)

    cancion = get_object_or_404(Cancion.objects.select_related('categoria'), pk=id)
    return JsonResponse({
        'ok': True,
        'song': {
            'id': cancion.pk,
            'numero': cancion.numero,
            'titulo': cancion.titulo,
            'categoria': cancion.categoria.nombre,
            'categoria_id': cancion.categoria_id,
            'letra': cancion.letra or '',
            'usa_capodastro': cancion.usa_capodastro,
            'traste_capodastro': cancion.traste_capodastro,
        }
    })


@staff_member_required(login_url='home')
def crear_cancion(request, id):
    """Crea una canción nueva dentro de la categoría que se está visitando."""
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Método no permitido.'}, status=405)

    categoria = get_object_or_404(Categoria, pk=id)
    titulo = request.POST.get('titulo', '').strip()
    letra = request.POST.get('letra', '').strip()
    numero_texto = request.POST.get('numero', '').strip()
    usa_capodastro = request.POST.get('usa_capodastro') == 'on'
    traste_texto = request.POST.get('traste_capodastro', '').strip()

    if not titulo or not letra:
        return JsonResponse({
            'ok': False,
            'error': 'El título y la letra son obligatorios.'
        }, status=400)

    numero = None
    if numero_texto:
        try:
            numero = int(numero_texto)
            if numero < 1:
                raise ValueError
        except (ValueError, TypeError):
            return JsonResponse({
                'ok': False,
                'error': 'El número debe ser un entero mayor que cero.'
            }, status=400)
        if Cancion.objects.filter(numero=numero).exists():
            return JsonResponse({
                'ok': False,
                'error': f'Ya existe una canción con el número {numero}.'
            }, status=400)

    traste = None
    if usa_capodastro:
        if traste_texto:
            try:
                traste = int(traste_texto)
                if traste < 1:
                    raise ValueError
            except (ValueError, TypeError):
                return JsonResponse({
                    'ok': False,
                    'error': 'El traste del capodastro debe ser un entero mayor que cero.'
                }, status=400)
        else:
            return JsonResponse({
                'ok': False,
                'error': 'Indica el traste del capodastro.'
            }, status=400)

    cancion = Cancion.objects.create(
        numero=numero,
        categoria=categoria,
        titulo=titulo,
        letra=letra,
        usa_capodastro=usa_capodastro,
        traste_capodastro=traste if usa_capodastro else None,
    )

    return JsonResponse({
        'ok': True,
        'message': 'La canción se creó correctamente.',
        'song': {
            'id': cancion.pk,
            'numero': cancion.numero,
            'titulo': cancion.titulo,
            'categoria': categoria.nombre,
            'categoria_id': categoria.pk,
            'letra': cancion.letra,
            'usa_capodastro': cancion.usa_capodastro,
            'traste_capodastro': cancion.traste_capodastro,
        }
    }, status=201)


def categoria(request,id):

    categoria=Categoria.objects.get(id=id)

    canciones= Cancion.objects.filter(
        categoria=categoria
    )

    acordes = [
        'DO','RE','MI','FA','SOL','LA','SI',
        'Do','Re','Mi','Fa','Sol','La','Si',
        'DOM','REM','MIM','FAM','SOLM','LAM','SIM',
        'DO#','RE#','FA#','SOL#','LA#',
        'DOm','REm','MIm','FAm','SOLm','LAm','SIm',
        'DO7','RE7','MI7','FA7','SOL7','LA7','SI7',
        'DOB','REB','MIB','FAB','SOLB','LAB','SIB',
    ]

    # Escapa caracteres especiales (#, etc.)
    lista_acordes = '|'.join(map(re.escape, acordes))

    # Combinar lista personalizada + patrón internacional
    PATRON_ACORDES = rf'\b(?:{lista_acordes}|[A-G](?:#|b)?(?:m|7|m7|maj7|sus4|dim|add9)?)\b'

    for cancion in canciones:

        cancion.letra_coloreada = re.sub(
            PATRON_ACORDES,
            r'<span class="acorde">\g<0></span>',
            cancion.letra
        )




    return render(
        request,
        'categoria.html',
        {
            'categoria':categoria,
            'canciones':canciones
        }
    )

def exportar_pdf(request, id):
    """Genera un PDF descargable con la letra de una canción del cancionero."""
    from reportlab.platypus import Preformatted
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from django.utils.text import slugify
    from xml.sax.saxutils import escape as xml_escape
    import textwrap

    cancion = get_object_or_404(
        Cancion.objects.select_related('categoria'),
        pk=id
    )

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=22 * mm,
        bottomMargin=18 * mm,
        title=f'{cancion.numero or ""} - {cancion.titulo}',
        author='Emaús - Cancionero Digital',
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name='CancionPDFTitle',
        parent=styles['Title'],
        fontName='Helvetica-Bold',
        fontSize=19,
        leading=24,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#bd0026'),
        spaceAfter=5 * mm,
    ))
    styles.add(ParagraphStyle(
        name='CancionPDFMeta',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#555555'),
        spaceAfter=2 * mm,
    ))
    styles.add(ParagraphStyle(
        name='CancionPDFLetra',
        parent=styles['Code'],
        fontName='Courier',
        fontSize=9,
        leading=12,
        leftIndent=2 * mm,
        rightIndent=2 * mm,
        spaceAfter=0,
        textColor=colors.HexColor('#222222'),
    ))

    story = [
        Paragraph(
            xml_escape(f'{cancion.numero or ""} - {cancion.titulo}'),
            styles['CancionPDFTitle']
        ),
        Paragraph(
            f'Categoría: {xml_escape(cancion.categoria.nombre)}',
            styles['CancionPDFMeta']
        ),
    ]
    if cancion.usa_capodastro and cancion.traste_capodastro:
        story.append(Paragraph(
            f'Capodastro: traste {cancion.traste_capodastro}',
            styles['CancionPDFMeta']
        ))
    story.append(Spacer(1, 5 * mm))

    letra = (cancion.letra or '').replace('\r\n', '\n').replace('\r', '\n')
    max_chars = max(
        45,
        int((A4[0] - doc.leftMargin - doc.rightMargin - 4 * mm) / stringWidth('M', 'Courier', 9))
    )
    for linea in letra.split('\n'):
        if not linea:
            story.append(Spacer(1, 4))
            continue
        segmentos = textwrap.wrap(
            linea,
            width=max_chars,
            expand_tabs=False,
            replace_whitespace=False,
            drop_whitespace=False,
            break_long_words=True,
            break_on_hyphens=False,
        )
        for segmento in segmentos or [' ']:
            story.append(Preformatted(segmento or ' ', styles['CancionPDFLetra']))

    def pie_pagina(canvas, documento):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor('#dddddd'))
        canvas.line(20 * mm, 14 * mm, A4[0] - 20 * mm, 14 * mm)
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor('#666666'))
        canvas.drawString(20 * mm, 9 * mm, 'Emaús · Cancionero Digital')
        canvas.drawRightString(A4[0] - 20 * mm, 9 * mm, f'Página {documento.page}')
        canvas.restoreState()

    doc.build(story, onFirstPage=pie_pagina, onLaterPages=pie_pagina)
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    nombre_archivo = slugify(cancion.titulo) or f'cancion-{cancion.pk}'
    response['Content-Disposition'] = f'attachment; filename="cancion-{cancion.pk}-{nombre_archivo}.pdf"'
    buffer.close()
    return response


def cerrar_sesion(request):

    logout(request)

    return redirect('home')

def guardar_cancion(request, id):

    if request.method == "POST":

        cancion = Cancion.objects.get(
            id=id
        )

        data = json.loads(
            request.body
        )

        cancion.letra = data.get("letra", cancion.letra)
        if "usa_capodastro" in data:
            usa_capo = bool(data["usa_capodastro"])
            traste = data.get("traste_capodastro")
            if usa_capo and traste in (None, ""):
                return JsonResponse({"ok": False, "error": "Indica el número de traste del capodastro."}, status=400)
            if usa_capo:
                try:
                    traste = int(traste)
                except (TypeError, ValueError):
                    return JsonResponse({"ok": False, "error": "El traste debe ser un número entre 1 y 12."}, status=400)
                if not 1 <= traste <= 12:
                    return JsonResponse({"ok": False, "error": "El traste debe estar entre 1 y 12."}, status=400)
            cancion.usa_capodastro = usa_capo
            cancion.traste_capodastro = traste if usa_capo else None

        cancion.save()

        return JsonResponse({
            "ok": True,
            "usa_capodastro": cancion.usa_capodastro,
            "traste_capodastro": cancion.traste_capodastro,
        })

    return JsonResponse({
        "ok": False
    })

@staff_member_required(login_url='home')
def grupos_servidores(request):
    """Panel de gestión de grupos e integrantes, exclusivo para usuarios staff."""
    if request.method == 'POST':
        accion = request.POST.get('accion')
        if accion == 'crear_grupo':
            nombre = request.POST.get('nombre', '').strip()
            tipo = request.POST.get('tipo', 'permanente')
            descripcion = request.POST.get('descripcion', '').strip()
            integrantes_ids = request.POST.getlist('integrantes')
            if not nombre:
                messages.error(request, 'Escribe el nombre del grupo.')
            elif tipo not in ('permanente', 'temporal'):
                messages.error(request, 'El tipo de grupo no es válido.')
            elif Grupo.objects.filter(nombre__iexact=nombre).exists():
                messages.error(request, 'Ya existe un grupo con ese nombre.')
            else:
                grupo = Grupo.objects.create(nombre=nombre, tipo=tipo, descripcion=descripcion)
                grupo.integrantes.set(Perfil.objects.filter(pk__in=integrantes_ids))
                messages.success(request, f'El grupo «{grupo.nombre}» fue creado correctamente.')
        elif accion == 'actualizar_integrantes':
            grupo = get_object_or_404(Grupo, pk=request.POST.get('grupo_id'))
            integrantes_ids = request.POST.getlist('integrantes')
            grupo.integrantes.set(Perfil.objects.filter(pk__in=integrantes_ids))
            messages.success(request, f'Integrantes de «{grupo.nombre}» actualizados.')
        elif accion == 'agregar_integrante':
            grupo = get_object_or_404(Grupo, pk=request.POST.get('grupo_id'))
            perfil = get_object_or_404(Perfil, pk=request.POST.get('perfil_id'))
            grupo.integrantes.add(perfil)
            messages.success(request, f'{perfil.nombres} fue agregado a «{grupo.nombre}».')
        elif accion == 'quitar_integrante':
            grupo = get_object_or_404(Grupo, pk=request.POST.get('grupo_id'))
            perfil = get_object_or_404(Perfil, pk=request.POST.get('perfil_id'))
            grupo.integrantes.remove(perfil)
            if grupo.lider_id == perfil.pk:
                grupo.lider = None
                grupo.save(update_fields=['lider'])
            messages.success(request, f'{perfil.nombres} fue retirado de «{grupo.nombre}».')
        elif accion == 'establecer_lider':
            grupo = get_object_or_404(Grupo, pk=request.POST.get('grupo_id'))
            perfil_id = request.POST.get('perfil_id')
            if perfil_id:
                perfil = get_object_or_404(Perfil, pk=perfil_id)
                if not grupo.integrantes.filter(pk=perfil.pk).exists():
                    messages.error(request, 'El líder debe ser un servidor agregado a este grupo.')
                    return redirect('grupos_servidores')
                grupo.lider = perfil
                grupo.save(update_fields=['lider'])
                messages.success(request, f'{perfil.nombres} es ahora líder de «{grupo.nombre}».')
            else:
                grupo.lider = None
                grupo.save(update_fields=['lider'])
                messages.success(request, f'Se quitó el líder de «{grupo.nombre}».')
        elif accion == 'cambiar_estado':
            grupo = get_object_or_404(Grupo, pk=request.POST.get('grupo_id'))
            grupo.activo = not grupo.activo
            grupo.save(update_fields=['activo'])
            messages.success(request, f'Estado del grupo «{grupo.nombre}» actualizado.')
        return redirect('grupos_servidores')

    grupos = Grupo.objects.prefetch_related('integrantes').order_by('tipo', 'nombre')
    perfiles = Perfil.objects.select_related('usuario').order_by('nombres')
    return render(request, 'grupos_servidores.html', {'grupos': grupos, 'perfiles': perfiles})


@staff_member_required(login_url='home')
def exportar_grupos_pdf(request):
    """Genera un listado elegante de los grupos activos y sus servidores."""
    from django.contrib.staticfiles import finders
    from reportlab.lib.utils import ImageReader
    from svglib.svglib import svg2rlg
    from reportlab.graphics import renderPDF
    from xml.sax.saxutils import escape

    buffer = BytesIO()
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="listado_grupos_y_servidores.pdf"'

    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=17*mm, leftMargin=17*mm,
        topMargin=35*mm, bottomMargin=17*mm
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name='ListadoTitle', parent=styles['Title'], fontName='Helvetica-Bold',
        fontSize=19, leading=23, textColor=colors.HexColor('#bd0026'),
        alignment=TA_LEFT, spaceAfter=2*mm
    ))
    styles.add(ParagraphStyle(
        name='ListadoSubtitle', parent=styles['Normal'], fontName='Helvetica',
        fontSize=9, leading=13, textColor=colors.HexColor('#626262'), spaceAfter=5*mm
    ))
    styles.add(ParagraphStyle(
        name='GrupoTitle', parent=styles['Heading2'], fontName='Helvetica-Bold',
        fontSize=12, leading=15, textColor=colors.HexColor('#bd0026'),
        spaceBefore=4*mm, spaceAfter=1.5*mm, keepWithNext=True
    ))
    styles.add(ParagraphStyle(
        name='ServidorText', parent=styles['BodyText'], fontName='Helvetica',
        fontSize=9, leading=12
    ))
    styles.add(ParagraphStyle(
        name='SmallMuted', parent=styles['BodyText'], fontName='Helvetica',
        fontSize=8, leading=10, textColor=colors.HexColor('#626262')
    ))

    styles['ListadoTitle'].alignment = TA_CENTER
    styles['ListadoSubtitle'].alignment = TA_CENTER
    story = [
        Paragraph('LISTADO DE GRUPOS Y SERVIDORES', styles['ListadoTitle']),
        Paragraph('Ministerio de Música · Emaús', styles['ListadoSubtitle']),
    ]
    grupos = Grupo.objects.filter(activo=True).prefetch_related('integrantes').order_by('tipo', 'nombre')
    total_servidores = sum(grupo.integrantes.count() for grupo in grupos)
    story.append(Paragraph(
        '{} grupo(s) activo(s) · {} asignación(es) de servidor'.format(grupos.count(), total_servidores),
        styles['SmallMuted']
    ))
    story.append(Spacer(1, 3*mm))

    if not grupos.exists():
        story.append(Paragraph('No hay grupos activos registrados.', styles['ServidorText']))
    else:
        for grupo in grupos:
            integrantes = list(grupo.integrantes.all().order_by('nombres'))
            nombre_lider = grupo.lider.nombres if grupo.lider_id else 'Sin líder asignado'
            story.append(Paragraph(
                '{} <font size="9" color="#626262">· {} · {} servidor(es)</font><br/><font size="9" color="#333333">Líder: {}</font>'.format(
                    escape(grupo.nombre), escape(grupo.get_tipo_display()), len(integrantes), escape(nombre_lider)
                ),
                styles['GrupoTitle']
            ))
            rows = [['N.º', 'Nombre del servidor', 'Teléfono', 'Email', 'Instrumento / voz']]
            if integrantes:
                for numero, perfil in enumerate(integrantes, start=1):
                    instrumentos = list(perfil.instrumentos.filter(activo=True).values_list('nombre', flat=True))
                    if perfil.es_cantante:
                        instrumentos.append('Canto')
                    instrumento_voz = ' y '.join(instrumentos) if instrumentos else '—'
                    rows.append([
                        str(numero),
                        Paragraph(escape(str(perfil.nombres or '')), styles['ServidorText']),
                        Paragraph(escape(str(perfil.telefono or '—')), styles['ServidorText']),
                        Paragraph(escape(str(perfil.correo or '—')), styles['ServidorText']),
                        Paragraph(escape(instrumento_voz), styles['ServidorText'])
                    ])
            else:
                rows.append(['', Paragraph('Sin servidores asignados', styles['SmallMuted']), '', '', ''])
            table = Table(rows, colWidths=[9*mm, 49*mm, 25*mm, 42*mm, 36*mm], repeatRows=1, hAlign='LEFT')
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#25252b')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.45, colors.HexColor('#dedee2')),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f7f7f9')]),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ]))
            story.extend([table, Spacer(1, 2*mm)])

    def dibujar_cabecera(canvas, documento):
        canvas.saveState()
        canvas.setFillColor(colors.HexColor('#bd0026'))
        canvas.rect(0, A4[1] - 7*mm, A4[0], 7*mm, fill=1, stroke=0)
        logo_path = finders.find('images/logomio_negro.svg')
        if logo_path:
            try:
                logo_drawing = svg2rlg(logo_path)
                if logo_drawing:
                    scale = min((68*mm) / max(logo_drawing.width, 1), (25*mm) / max(logo_drawing.height, 1))
                    logo_drawing.width *= scale
                    logo_drawing.height *= scale
                    logo_drawing.scale(scale, scale)
                    logo_x = (A4[0] - logo_drawing.width) / 2
                    logo_y = A4[1] - 34*mm
                    renderPDF.draw(logo_drawing, canvas, logo_x, logo_y)
            except Exception:
                pass
        canvas.setStrokeColor(colors.HexColor('#e1e1e5'))
        canvas.line(17*mm, A4[1]-36*mm, A4[0]-17*mm, A4[1]-36*mm)
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor('#666666'))
        canvas.drawString(17*mm, 9*mm, 'Emaús · Listado de grupos y servidores')
        canvas.drawRightString(A4[0]-17*mm, 9*mm, 'Página {}'.format(documento.page))
        canvas.restoreState()

    doc.build(story, onFirstPage=dibujar_cabecera, onLaterPages=dibujar_cabecera)
    response.write(buffer.getvalue())
    buffer.close()
    return response

@staff_member_required(login_url='home')
def servidores(request):
    """Gestión de cuentas y perfiles de servidores; solo usuarios staff."""
    editar_id = request.GET.get('editar')
    perfil_editar = get_object_or_404(Perfil, pk=editar_id) if editar_id else None

    if request.method == 'POST':
        accion = request.POST.get('accion')
        if accion in ('crear_servidor', 'editar_servidor'):
            perfil_id = request.POST.get('perfil_id')
            perfil = get_object_or_404(Perfil, pk=perfil_id) if perfil_id else None
            nombres = request.POST.get('nombres', '').strip()
            correo = request.POST.get('correo', '').strip()
            telefono = request.POST.get('telefono', '').strip()
            username = request.POST.get('username', '').strip()
            password = request.POST.get('password', '')
            fecha_nacimiento = request.POST.get('fecha_nacimiento')
            instrumentos_ids = request.POST.getlist('instrumentos')
            es_cantante = request.POST.get('es_cantante') == 'on'

            if not all([nombres, correo, username, fecha_nacimiento]):
                messages.error(request, 'Completa todos los campos obligatorios.')
            elif not perfil and not password:
                messages.error(request, 'Define una contraseña para la nueva cuenta.')
            elif User.objects.filter(username=username).exclude(pk=perfil.usuario_id if perfil else None).exists():
                messages.error(request, 'Ese nombre de usuario ya está ocupado.')
            elif Perfil.objects.filter(correo__iexact=correo).exclude(pk=perfil.pk if perfil else None).exists():
                messages.error(request, 'Ese correo ya está registrado en otro perfil.')
            else:
                try:
                    nacimiento = date.fromisoformat(fecha_nacimiento)
                    with transaction.atomic():
                        if perfil:
                            usuario = perfil.usuario
                            usuario.username = username
                            usuario.email = correo
                            usuario.first_name = nombres
                            if password:
                                usuario.set_password(password)
                            usuario.save()
                            perfil.nombres = nombres
                            perfil.correo = correo
                            perfil.telefono = telefono
                            perfil.fecha_nacimiento = nacimiento
                            perfil.es_cantante = es_cantante
                            perfil.save()
                            perfil.instrumentos.set(Instrumento.objects.filter(pk__in=instrumentos_ids, activo=True))
                            mensaje = f'Datos de {nombres} actualizados.'
                        else:
                            usuario = User.objects.create_user(username=username, password=password, email=correo, first_name=nombres, is_active=True)
                            # El grupo de perfil es un campo heredado; la asignación real se gestiona desde cada grupo.
                            perfil = Perfil.objects.create(usuario=usuario, nombres=nombres, correo=correo, telefono=telefono, grupo=1, fecha_nacimiento=nacimiento, es_cantante=es_cantante)
                            perfil.instrumentos.set(Instrumento.objects.filter(pk__in=instrumentos_ids, activo=True))
                            mensaje = f'Servidor {nombres} creado con su cuenta de acceso.'
                    messages.success(request, mensaje)
                    return redirect('servidores')
                except (ValueError, TypeError):
                    messages.error(request, 'La fecha de nacimiento no es válida.')
        elif accion == 'cambiar_estado_servidor':
            perfil = get_object_or_404(Perfil.objects.select_related('usuario'), pk=request.POST.get('perfil_id'))
            perfil.usuario.is_active = not perfil.usuario.is_active
            perfil.usuario.save(update_fields=['is_active'])
            messages.success(request, f'Cuenta de {perfil.nombres}: ' + ('activada.' if perfil.usuario.is_active else 'desactivada.'))
            return redirect('servidores')
        elif accion == 'eliminar_servidor':
            perfil = get_object_or_404(Perfil.objects.select_related('usuario'), pk=request.POST.get('perfil_id'))
            nombre_servidor = perfil.nombres
            usuario = perfil.usuario
            with transaction.atomic():
                # Eliminar el usuario también elimina su perfil por la relación OneToOne.
                usuario.delete()
            messages.success(request, f'El servidor {nombre_servidor} y su cuenta de acceso fueron eliminados.')
            return redirect('servidores')

    perfiles = Perfil.objects.select_related('usuario').prefetch_related('grupos_asignados').order_by('nombres')
    return render(request, 'servidores.html', {
        'perfiles': perfiles,
        'perfil_editar': perfil_editar,
        'instrumentos': Instrumento.objects.filter(activo=True),
        'instrumentos_perfil': list(perfil_editar.instrumentos.values_list('id', flat=True)) if perfil_editar else [],
    })


@staff_member_required(login_url='home')
def exportar_servidores_pdf(request):
    """Exporta todos los servidores registrados a un PDF en formato horizontal."""
    from reportlab.lib.pagesizes import landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph
    from xml.sax.saxutils import escape
    from django.contrib.staticfiles import finders
    from svglib.svglib import svg2rlg
    from reportlab.graphics import renderPDF

    perfiles = list(
        Perfil.objects.select_related('usuario')
        .prefetch_related('instrumentos')
        .order_by('nombres')
    )

    buffer = BytesIO()
    page_size = landscape(A4)
    doc = SimpleDocTemplate(
        buffer,
        pagesize=page_size,
        rightMargin=12 * mm,
        leftMargin=12 * mm,
        topMargin=27 * mm,
        bottomMargin=17 * mm,
        title='Listado de servidores - Emaús',
        author='Emaús - Ministerio de Música',
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name='ServidoresPDFTitle',
        parent=styles['Title'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#bd0026'),
        spaceAfter=2 * mm,
    ))
    styles.add(ParagraphStyle(
        name='ServidoresPDFSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#555555'),
        spaceAfter=5 * mm,
    ))
    styles.add(ParagraphStyle(
        name='ServidoresPDFCell',
        parent=styles['BodyText'],
        fontName='Helvetica',
        fontSize=7.2,
        leading=9,
        wordWrap='CJK',
    ))
    styles.add(ParagraphStyle(
        name='ServidoresPDFHeader',
        parent=styles['BodyText'],
        fontName='Helvetica-Bold',
        fontSize=7,
        leading=8,
        textColor=colors.white,
        alignment=TA_CENTER,
    ))

    story = [
        Paragraph('LISTADO DE SERVIDORES', styles['ServidoresPDFTitle']),
        Paragraph(
            f'Ministerio de Música · Emaús · {len(perfiles)} servidor(es) registrado(s)',
            styles['ServidoresPDFSubtitle']
        ),
    ]

    header = ['N.º', 'Servidor', 'Usuario', 'Correo electrónico', 'Teléfono',
              'Nacimiento', 'Estado', 'Instrumentos / voz']
    rows = [[Paragraph(escape(item), styles['ServidoresPDFHeader']) for item in header]]

    for numero, perfil in enumerate(perfiles, start=1):
        instrumentos = [instrumento.nombre for instrumento in perfil.instrumentos.all()]
        if perfil.es_cantante:
            instrumentos.append('Canto')
        texto_instrumentos = ', '.join(instrumentos) if instrumentos else '—'
        estado = 'Activo' if perfil.usuario.is_active else 'Inactivo'
        nacimiento = perfil.fecha_nacimiento.strftime('%d/%m/%Y') if perfil.fecha_nacimiento else '—'
        datos = [
            str(numero),
            perfil.nombres or '—',
            perfil.usuario.username or '—',
            perfil.correo or '—',
            perfil.telefono or '—',
            nacimiento,
            estado,
            texto_instrumentos,
        ]
        rows.append([Paragraph(escape(str(value)), styles['ServidoresPDFCell']) for value in datos])

    if not perfiles:
        rows.append([
            Paragraph('—', styles['ServidoresPDFCell']),
            Paragraph('No hay servidores registrados.', styles['ServidoresPDFCell']),
            Paragraph('', styles['ServidoresPDFCell']),
            Paragraph('', styles['ServidoresPDFCell']),
            Paragraph('', styles['ServidoresPDFCell']),
            Paragraph('', styles['ServidoresPDFCell']),
            Paragraph('', styles['ServidoresPDFCell']),
            Paragraph('', styles['ServidoresPDFCell']),
        ])

    col_widths = [8*mm, 37*mm, 23*mm, 49*mm, 25*mm, 22*mm, 19*mm, 90*mm]
    table = Table(rows, colWidths=col_widths, repeatRows=1, hAlign='LEFT')
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#25252b')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#d5d5da')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (5, 1), (6, -1), 'CENTER'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1),
         [colors.white, colors.HexColor('#f5f5f7')]),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(table)

    def dibujar_pie(canvas, documento):
        canvas.saveState()
        canvas.setFillColor(colors.HexColor('#bd0026'))
        canvas.rect(0, page_size[1] - 5 * mm, page_size[0], 5 * mm, fill=1, stroke=0)

        # Logo oficial de Emaús centrado en el encabezado de cada página.
        logo_path = finders.find('images/logomio_negro.svg')
        if logo_path:
            try:
                logo_drawing = svg2rlg(logo_path)
                if logo_drawing:
                    scale = min(
                        (48 * mm) / max(logo_drawing.width, 1),
                        (14 * mm) / max(logo_drawing.height, 1),
                    )
                    logo_drawing.width *= scale
                    logo_drawing.height *= scale
                    logo_drawing.scale(scale, scale)
                    logo_x = (page_size[0] - logo_drawing.width) / 2
                    logo_y = page_size[1] - 22 * mm
                    renderPDF.draw(logo_drawing, canvas, logo_x, logo_y)
            except Exception:
                # El informe seguirá generándose aunque el SVG no se pueda renderizar.
                pass

        canvas.setStrokeColor(colors.HexColor('#dddddd'))
        canvas.line(12 * mm, 12 * mm, page_size[0] - 12 * mm, 12 * mm)
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor('#666666'))
        canvas.drawString(12 * mm, 7 * mm, 'Emaús · Listado de servidores')
        canvas.drawRightString(page_size[0] - 12 * mm, 7 * mm, f'Página {documento.page}')
        canvas.restoreState()

    doc.build(story, onFirstPage=dibujar_pie, onLaterPages=dibujar_pie)
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="listado_servidores_emaus.pdf"'
    buffer.close()
    return response

