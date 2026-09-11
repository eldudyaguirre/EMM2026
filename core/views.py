from django.shortcuts import render,get_object_or_404
from .models import Categoria, Cancion
from django.utils.safestring import mark_safe
import re
from django.contrib.auth import authenticate, login
from django.shortcuts import render, redirect
from django.contrib.auth import logout
from django.http import JsonResponse
import json


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