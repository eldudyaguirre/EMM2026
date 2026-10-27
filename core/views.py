from django.shortcuts import render,get_object_or_404
from .models import Categoria, Cancion, Servicio, Grupo, Perfil
from django.contrib.auth.models import User
from django.db import transaction
from datetime import date
from django.utils.safestring import mark_safe
import re
from django.contrib.auth import authenticate, login
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.shortcuts import render, redirect
from django.contrib.auth import logout
from django.http import JsonResponse, HttpResponse
import json
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether


def home(request):

    if request.method == 'POST':

        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(
            request,
            username=username,
            password=password
        )

        if user is not None:

            # Verificar si está activo
            if user.is_active:

                login(
                    request,
                    user
                )

                return redirect(
                    'loginin'
                )

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
    return render(request, 'loginin.html')


def calendario(request):
    """Muestra los servicios activos guardados en la base de datos."""
    servicios = [
        {
            'titulo': servicio.titulo,
            'grupo': servicio.grupo.nombre,
            'fecha': servicio.fecha.isoformat(),
            'hora_inicio': servicio.hora_inicio.strftime('%H:%M'),
            'hora_fin': servicio.hora_fin.strftime('%H:%M') if servicio.hora_fin else '',
            'lugar': servicio.lugar,
            'observaciones': servicio.observaciones,
            'tipo_grupo': servicio.grupo.tipo,
        }
        for servicio in Servicio.objects.filter(
            activo=True,
            grupo__activo=True
        ).select_related('grupo').order_by('fecha', 'hora_inicio')
    ]
    return render(request, 'calendario.html', {'servicios': servicios})


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

        cancion.letra = data["letra"]

        cancion.save()

        return JsonResponse({
            "ok": True
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
            messages.success(request, f'{perfil.nombres} fue retirado de «{grupo.nombre}».')
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
    """Exporta grupos activos y sus servidores con casillas para pasar lista."""
    buffer = BytesIO()
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="listado_servidores_por_grupo.pdf"'

    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=16*mm, leftMargin=16*mm,
        topMargin=16*mm, bottomMargin=16*mm
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name='EmausTitle', parent=styles['Title'],
        fontName='Helvetica-Bold', fontSize=18, leading=22,
        textColor=colors.HexColor('#bd0026'), alignment=TA_CENTER,
        spaceAfter=5*mm
    ))
    styles.add(ParagraphStyle(
        name='GroupHeading', parent=styles['Heading2'],
        fontName='Helvetica-Bold', fontSize=12, leading=15,
        textColor=colors.HexColor('#222222'), spaceBefore=5*mm,
        spaceAfter=2*mm, keepWithNext=True
    ))
    styles.add(ParagraphStyle(
        name='SmallText', parent=styles['BodyText'],
        fontName='Helvetica', fontSize=8, leading=10
    ))

    story = [
        Paragraph('EMAÚS · LISTA DE ASISTENCIA', styles['EmausTitle']),
        Paragraph('Listado de servidores por grupo activo para reuniones generales.', styles['BodyText']),
        Spacer(1, 3*mm),
        Paragraph('Fecha: ____________________________________   Reunión: ____________________________________', styles['BodyText']),
        Spacer(1, 4*mm),
    ]
    grupos = Grupo.objects.filter(activo=True).prefetch_related('integrantes').order_by('tipo', 'nombre')
    if not grupos.exists():
        story.append(Paragraph('No hay grupos activos registrados.', styles['BodyText']))
    else:
        for grupo in grupos:
            integrantes = list(grupo.integrantes.all().order_by('nombres'))
            story.append(Paragraph(grupo.nombre, styles['GroupHeading']))
            story.append(Paragraph('Tipo: {} · Servidores: {}'.format(
                grupo.get_tipo_display(), len(integrantes)
            ), styles['SmallText']))
            rows = [['#', 'Servidor', 'Teléfono', 'Asistencia', 'Observaciones']]
            if integrantes:
                for numero, perfil in enumerate(integrantes, start=1):
                    rows.append([
                        str(numero),
                        Paragraph(str(perfil.nombres or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'), styles['SmallText']),
                        str(perfil.telefono or '—'),
                        '☐',
                        ''
                    ])
            else:
                rows.append(['', Paragraph('Sin servidores asignados', styles['SmallText']), '', '', ''])
            table = Table(rows, colWidths=[9*mm, 55*mm, 28*mm, 23*mm, 43*mm], repeatRows=1, hAlign='LEFT')
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#bd0026')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('LEADING', (0, 0), (-1, -1), 10),
                ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#b8b8b8')),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                ('ALIGN', (3, 1), (3, -1), 'CENTER'),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ]))
            story.extend([table, Spacer(1, 3*mm)])

    def pie_pagina(canvas, documento):
        canvas.saveState()
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor('#666666'))
        canvas.drawString(16*mm, 9*mm, 'Emaús · Control de asistencia')
        canvas.drawRightString(A4[0] - 16*mm, 9*mm, 'Página {}'.format(documento.page))
        canvas.restoreState()

    doc.build(story, onFirstPage=pie_pagina, onLaterPages=pie_pagina)
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
            grupo_num = request.POST.get('grupo')
            fecha_nacimiento = request.POST.get('fecha_nacimiento')
            grupos_ids = request.POST.getlist('grupos_servicio')

            if not all([nombres, correo, username, grupo_num, fecha_nacimiento]):
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
                            perfil.grupo = int(grupo_num)
                            perfil.fecha_nacimiento = nacimiento
                            perfil.save()
                            mensaje = f'Datos de {nombres} actualizados.'
                        else:
                            usuario = User.objects.create_user(username=username, password=password, email=correo, first_name=nombres, is_active=True)
                            perfil = Perfil.objects.create(usuario=usuario, nombres=nombres, correo=correo, telefono=telefono, grupo=int(grupo_num), fecha_nacimiento=nacimiento)
                            mensaje = f'Servidor {nombres} creado con su cuenta de acceso.'
                        for grupo in Grupo.objects.filter(integrantes=perfil):
                            grupo.integrantes.remove(perfil)
                        for grupo in Grupo.objects.filter(pk__in=grupos_ids, activo=True):
                            grupo.integrantes.add(perfil)
                    messages.success(request, mensaje)
                    return redirect('servidores')
                except (ValueError, TypeError):
                    messages.error(request, 'La fecha de nacimiento o el grupo no son válidos.')
        elif accion == 'cambiar_estado_servidor':
            perfil = get_object_or_404(Perfil.objects.select_related('usuario'), pk=request.POST.get('perfil_id'))
            perfil.usuario.is_active = not perfil.usuario.is_active
            perfil.usuario.save(update_fields=['is_active'])
            messages.success(request, f'Cuenta de {perfil.nombres}: ' + ('activada.' if perfil.usuario.is_active else 'desactivada.'))
            return redirect('servidores')

    perfiles = Perfil.objects.select_related('usuario').prefetch_related('grupos_asignados').order_by('nombres')
    return render(request, 'servidores.html', {
        'perfiles': perfiles,
        'grupos': Grupo.objects.filter(activo=True).order_by('nombre'),
        'grupos_perfil': list(perfil_editar.grupos_asignados.values_list('id', flat=True)) if perfil_editar else [],
        'grupos_permanentes': Perfil.GRUPOS,
        'perfil_editar': perfil_editar,
    })
