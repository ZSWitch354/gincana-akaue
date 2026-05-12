from flask import (
    Flask,
    render_template,
    request,
    redirect,
    session,
    flash,
    send_from_directory
)

import sqlite3
from datetime import datetime
import os
import uuid
import hashlib

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

app = Flask(__name__)

app.secret_key = "akaue_master_secure"

META = 60000
META_MINIMA = META * 0.005

UPLOAD_FOLDER = 'uploads'

ALLOWED_EXTENSIONS = {
    'png',
    'jpg',
    'jpeg',
    'pdf'
}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# ======================================
# BANCO
# ======================================

conn = sqlite3.connect(
    'banco.db',
    check_same_thread=False
)

cursor = conn.cursor()

# ======================================
# USUÁRIOS
# ======================================

cursor.execute('''
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario TEXT UNIQUE,
    senha TEXT,
    cargo TEXT
)
''')

# ======================================
# PARTICIPANTES
# ======================================

cursor.execute('''
CREATE TABLE IF NOT EXISTS participantes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    telefone TEXT
)
''')

# ======================================
# ARRECADAÇÕES
# ======================================

cursor.execute('''
CREATE TABLE IF NOT EXISTS arrecadacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    participante_id INTEGER,
    metodo TEXT,
    valor REAL,
    responsavel TEXT,
    comprovante TEXT,
    hash_comprovante TEXT,
    ip TEXT,
    data TEXT,
    status TEXT,
    admin_aprovou TEXT
)
''')

# ======================================
# LOGS
# ======================================

cursor.execute('''
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario TEXT,
    acao TEXT,
    data TEXT
)
''')

conn.commit()

# ======================================
# SUPER ADMIN
# ======================================

cursor.execute(
    "SELECT * FROM usuarios WHERE usuario='master'"
)

master = cursor.fetchone()

if not master:

    senha_hash = generate_password_hash(
        'Master@2026'
    )

    cursor.execute('''
    INSERT INTO usuarios
    (usuario, senha, cargo)
    VALUES (?, ?, ?)
    ''', (
        'master',
        senha_hash,
        'superadmin'
    ))

    conn.commit()

# ======================================
# FUNÇÕES
# ======================================

def registrar_log(usuario, acao):

    data = datetime.now().strftime(
        '%d/%m/%Y %H:%M'
    )

    novo_cursor = conn.cursor()

    novo_cursor.execute('''
    INSERT INTO logs
    (usuario, acao, data)
    VALUES (?, ?, ?)
    ''', (
        usuario,
        acao,
        data
    ))

    conn.commit()

def permitido(nome_arquivo):

    return '.' in nome_arquivo and \
           nome_arquivo.rsplit(
               '.', 1
           )[1].lower() in ALLOWED_EXTENSIONS

def gerar_hash_arquivo(caminho):

    sha256 = hashlib.sha256()

    with open(caminho, "rb") as f:

        for bloco in iter(
            lambda: f.read(4096),
            b""
        ):

            sha256.update(bloco)

    return sha256.hexdigest()

# ======================================
# LOGIN
# ======================================

@app.route('/', methods=['GET', 'POST'])

def login():

    erro = None

    if request.method == 'POST':

        usuario = request.form['usuario']

        senha = request.form['senha']

        cursor.execute(
            'SELECT * FROM usuarios WHERE usuario=?',
            (usuario,)
        )

        user = cursor.fetchone()

        if user and check_password_hash(
            user[2],
            senha
        ):

            session['logado'] = True

            session['usuario'] = user[1]

            session['cargo'] = user[3]

            registrar_log(
                user[1],
                'Login no sistema'
            )

            return redirect('/painel')

        else:

            erro = 'Usuário ou senha incorretos'

    return render_template(
        'login.html',
        erro=erro
    )

# ======================================
# PAINEL
# ======================================

@app.route('/painel')

def painel():

    if 'logado' not in session:
        return redirect('/')

    cursor.execute(
        'SELECT * FROM participantes'
    )

    participantes = cursor.fetchall()

    cursor.execute('''
    SELECT
        participantes.id,
        participantes.nome,
        IFNULL(SUM(arrecadacoes.valor),0)

    FROM participantes

    LEFT JOIN arrecadacoes

    ON participantes.id =
    arrecadacoes.participante_id

    AND arrecadacoes.status='Aprovado'

    GROUP BY participantes.id

    ORDER BY
    IFNULL(SUM(arrecadacoes.valor),0)
    DESC
    ''')

    ranking = cursor.fetchall()

    ranking_final = []

    total_geral = 0

    for r in ranking:

        total_geral += r[2]

        status = 'Atingiu'

        if r[2] < META_MINIMA:
            status = 'Não atingiu'

        ranking_final.append({

            'nome': r[1],

            'total': round(r[2], 2),

            'status': status

        })

    porcentagem = (
        total_geral / META
    ) * 100

    if porcentagem > 100:
        porcentagem = 100

    return render_template(

        'painel.html',

        participantes=participantes,

        ranking=ranking_final,

        total=round(total_geral, 2),

        meta=META,

        minimo=META_MINIMA,

        porcentagem=porcentagem,

        usuario=session['usuario'],

        cargo=session['cargo']

    )

# ======================================
# CRIAR USUÁRIO
# ======================================

@app.route(
    '/criar_usuario',
    methods=['GET', 'POST']
)

def criar_usuario():

    if 'logado' not in session:
        return redirect('/')

    if session['cargo'] != 'superadmin':
        return redirect('/painel')

    if request.method == 'POST':

        usuario = request.form['usuario']

        senha = request.form['senha']

        cargo = request.form['cargo']

        senha_hash = generate_password_hash(
            senha
        )

        try:

            cursor.execute('''
            INSERT INTO usuarios
            (usuario, senha, cargo)
            VALUES (?, ?, ?)
            ''', (
                usuario,
                senha_hash,
                cargo
            ))

            conn.commit()

            registrar_log(
                session['usuario'],
                f'Criou usuário {usuario}'
            )

            flash(
                'Usuário criado com sucesso'
            )

        except:

            flash('Usuário já existe')

    return render_template(
        'criar_usuario.html'
    )

# ======================================
# CADASTRAR PARTICIPANTE
# ======================================

@app.route(
    '/cadastrar',
    methods=['POST']
)

def cadastrar():

    if 'logado' not in session:
        return redirect('/')

    nome = request.form['nome']

    telefone = request.form['telefone']

    cursor.execute('''
    INSERT INTO participantes
    (nome, telefone)
    VALUES (?, ?)
    ''', (
        nome,
        telefone
    ))

    conn.commit()

    registrar_log(
        session['usuario'],
        f'Cadastrou participante {nome}'
    )

    return redirect('/painel')

# ======================================
# CONTRIBUIÇÃO
# ======================================

@app.route(
    '/contribuicao',
    methods=['POST']
)

def contribuicao():

    if 'logado' not in session:
        return redirect('/')

    participante_id = request.form[
        'participante_id'
    ]

    metodo = request.form['metodo']

    valor = float(request.form['valor'])

    responsavel = request.form[
        'responsavel'
    ]

    arquivo = request.files['comprovante']

    nome_arquivo = ''

    hash_arquivo = ''

    ip = request.remote_addr

    if valor <= 0:

        flash('Valor inválido')

        return redirect('/painel')

    if arquivo and permitido(
        arquivo.filename
    ):

        extensao = arquivo.filename.rsplit(
            '.', 1
        )[1].lower()

        nome_arquivo = f"{uuid.uuid4()}.{extensao}" 

        caminho = os.path.join(
            app.config['UPLOAD_FOLDER'],
            nome_arquivo
        )

        arquivo.save(caminho)

        hash_arquivo = gerar_hash_arquivo(
            caminho
        )

        cursor.execute('''
        SELECT * FROM arrecadacoes
        WHERE hash_comprovante=?
        ''', (
            hash_arquivo,
        ))

        fraude = cursor.fetchone()

        if fraude:

            os.remove(caminho)

            flash(
                'Comprovante duplicado detectado'
            )

            registrar_log(
                session['usuario'],
                'Tentativa de fraude'
            )

            return redirect('/painel')

    data = datetime.now().strftime(
        '%d/%m/%Y %H:%M'
    )

    cursor.execute('''
    INSERT INTO arrecadacoes
    (
        participante_id,
        metodo,
        valor,
        responsavel,
        comprovante,
        hash_comprovante,
        ip,
        data,
        status,
        admin_aprovou
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (

        participante_id,

        metodo,

        valor,

        responsavel,

        nome_arquivo,

        hash_arquivo,

        ip,

        data,

        'Pendente',

        ''

    ))

    conn.commit()

    registrar_log(
        session['usuario'],
        f'Registrou contribuição R${valor}'
    )

    flash(
        'Contribuição enviada para análise'
    )

    return redirect('/painel')

# ======================================
# ADMIN
# ======================================

@app.route('/admin')

def admin():

    if 'logado' not in session:
        return redirect('/')

    pesquisa = request.args.get(
        'pesquisa',
        ''
    )

    cursor.execute('''
    SELECT
        arrecadacoes.id,
        participantes.nome,
        arrecadacoes.metodo,
        arrecadacoes.valor,
        arrecadacoes.responsavel,
        arrecadacoes.comprovante,
        arrecadacoes.data,
        arrecadacoes.status,
        arrecadacoes.admin_aprovou

    FROM arrecadacoes

    INNER JOIN participantes

    ON participantes.id =
    arrecadacoes.participante_id

    WHERE participantes.nome LIKE ?

    ORDER BY arrecadacoes.id DESC
    ''', (
        f'%{pesquisa}%',
    ))

    vendas = cursor.fetchall()

    return render_template(
        'admin.html',
        vendas=vendas,
        pesquisa=pesquisa
    )

# ======================================
# APROVAR
# ======================================

@app.route('/aprovar/<int:id>')

def aprovar(id):

    if 'logado' not in session:
        return redirect('/')

    cursor.execute('''
    UPDATE arrecadacoes
    SET status=?, admin_aprovou=?
    WHERE id=?
    ''', (
        'Aprovado',
        session['usuario'],
        id
    ))

    conn.commit()

    registrar_log(
        session['usuario'],
        f'Aprovou contribuição {id}'
    )

    return redirect('/admin')

# ======================================
# RECUSAR
# ======================================

@app.route('/recusar/<int:id>')

def recusar(id):

    if 'logado' not in session:
        return redirect('/')

    cursor.execute('''
    UPDATE arrecadacoes
    SET status=?, admin_aprovou=?
    WHERE id=?
    ''', (
        'Recusado',
        session['usuario'],
        id
    ))

    conn.commit()

    registrar_log(
        session['usuario'],
        f'Recusou contribuição {id}'
    )

    return redirect('/admin')

# ======================================
# LOGOUT
# ======================================

@app.route('/logout')

def logout():

    session.clear()

    return redirect('/')

# ======================================
# EXECUTAR
# ======================================

@app.route('/uploads/<filename>')

def uploads(filename):

    return send_from_directory(
        app.config['UPLOAD_FOLDER'],
        filename
    )

if __name__ == '__main__':

    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True
    )
