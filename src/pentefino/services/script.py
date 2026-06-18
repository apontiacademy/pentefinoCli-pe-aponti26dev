import argparse
import re
import sys
from pathlib import Path

import pandas as pd


def normalizar_nome(nome: str) -> str:
    if not isinstance(nome, str):
        return ""
    return re.sub(r"\s+", " ", nome.strip()).lower()


def parsear_grupos(valor: str) -> tuple[str, str]:
    """Extrai estado e empresa do campo Grupos."""
    if not isinstance(valor, str):
        return ("", "")
    partes = valor.split(":", 1)
    if len(partes) < 2:
        return (valor.strip(), "")
    estado = partes[0].strip()
    resto = partes[1].strip()
    empresa = resto.split(" - ")[0].strip()
    return (estado, empresa)


def listar_csvs(diretorio: Path) -> list[Path]:
    csvs = sorted(diretorio.glob("*.csv"))
    if not csvs:
        print("Nenhum arquivo .csv encontrado no diretório atual.")
        sys.exit(1)
    print("\nArquivos CSV encontrados:")
    for i, f in enumerate(csvs, 1):
        print(f"  [{i}] {f.name}")
    return csvs


def selecionar_pasta_origem(padrao: Path) -> Path:
    print("\nEscolha a pasta de origem dos relatórios:")
    print(f"  (Deixe em branco para usar a pasta atual: {padrao.resolve()})")
    caminho_input = input("Digite o caminho da pasta ou deixe em branco: ").strip()

    if not caminho_input:
        return padrao.resolve()

    pasta = Path(caminho_input).expanduser().resolve()
    if not pasta.is_dir():
        print(f"ERRO: A pasta '{caminho_input}' não existe ou não é um diretório.")
        sys.exit(1)
    return pasta


def selecionar_planilha_geral(csvs: list[Path]) -> Path:
    while True:
        try:
            escolha = int(input("\nDigite o número da planilha GERAL de alunos: "))
            if 1 <= escolha <= len(csvs):
                return csvs[escolha - 1]
            print(f"  Digite um número entre 1 e {len(csvs)}.")
        except ValueError:
            print("  Entrada inválida. Digite apenas o número.")


def resolver_arquivo_csv(valor: str, diretorio: Path) -> Path:
    caminho = Path(valor).expanduser()

    candidatos = []
    if caminho.is_absolute():
        candidatos.append(caminho)
    else:
        candidatos.append(diretorio / caminho)
        candidatos.append(diretorio / caminho.name)
        candidatos.append(caminho)

    for candidato in candidatos:
        if candidato.exists() and candidato.is_file():
            return candidato.resolve()

    print(f"ERRO: Arquivo '{valor}' não encontrado na pasta '{diretorio}'.")
    sys.exit(1)


def carregar_alunos(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str).fillna("")
    cols = set(df.columns)

    if "residente" in cols:
        df["nome_completo"] = df["residente"].str.strip()
        df["_nome_norm"] = df["nome_completo"].apply(normalizar_nome)
        df["empresa"] = df["empresa"].str.strip() if "empresa" in cols else ""
        df["estado"] = ""
    elif {"Nome", "Sobrenome"}.issubset(cols):
        df["nome_completo"] = (df["Nome"] + " " + df["Sobrenome"]).str.strip()
        df["_nome_norm"] = df["nome_completo"].apply(normalizar_nome)
        if "Grupos" in cols:
            grupos_parsed = df["Grupos"].apply(parsear_grupos)
            df["estado"] = grupos_parsed.apply(lambda x: x[0])
            df["empresa"] = grupos_parsed.apply(lambda x: x[1])
        else:
            df["estado"] = ""
            df["empresa"] = ""
    else:
        print(
            "ERRO: A planilha geral precisa ter a coluna 'residente' ou as colunas 'Nome' e 'Sobrenome'."
        )
        sys.exit(1)

    return df[["nome_completo", "_nome_norm", "estado", "empresa"]].drop_duplicates(
        subset=["_nome_norm"]
    )


def carregar_relatorio(path: Path) -> set[str]:
    df = pd.read_csv(path, dtype=str).fillna("")

    if "Nome completo" not in df.columns:
        print(f"  AVISO: '{path.name}' não tem coluna 'Nome completo'. Pulando.")
        return set()

    return {normalizar_nome(n) for n in df["Nome completo"] if n.strip()}


def calcular_ausencias(
    df_alunos: pd.DataFrame, relatorios: dict[str, set[str]]
) -> pd.DataFrame:
    linhas = []
    for _, aluno in df_alunos.iterrows():
        ausentes = [
            nome_rel
            for nome_rel, respondentes in relatorios.items()
            if aluno["_nome_norm"] not in respondentes
        ]
        linhas.append(
            {
                "nome_completo": aluno["nome_completo"],
                "estado": aluno["estado"],
                "empresa": aluno["empresa"],
                "relatorios_ausentes": ", ".join(sorted(ausentes)),
                "total_ausencias": len(ausentes),
            }
        )
    return pd.DataFrame(linhas)


def calcular_presencas(
    df_alunos: pd.DataFrame, relatorios: dict[str, set[str]]
) -> pd.DataFrame:
    linhas = []
    for _, aluno in df_alunos.iterrows():
        presentes = [
            nome_rel
            for nome_rel, respondentes in relatorios.items()
            if aluno["_nome_norm"] in respondentes
        ]
        linhas.append(
            {
                "nome_completo": aluno["nome_completo"],
                "estado": aluno["estado"],
                "empresa": aluno["empresa"],
                "relatorios_feitos": ", ".join(sorted(presentes)),
                "total_feitos": len(presentes),
            }
        )
    return pd.DataFrame(linhas)


def selecionar_modo() -> str:
    print("\nEscolha o modo de visualização:")
    print("  [1] Não feitos (mostra quem não fez relatórios)")
    print("  [2] Feitos (mostra quem fez relatórios)")
    while True:
        try:
            escolha = int(input("\nDigite o número do modo: "))
            if escolha == 1:
                return "nao_feitos"
            elif escolha == 2:
                return "feitos"
            print("  Digite 1 ou 2.")
        except ValueError:
            print("  Entrada inválida. Digite apenas o número.")


def selecionar_caminho_output(diretorio: Path) -> Path:
    print("\nEscolha o caminho para salvar o arquivo de resultado:")
    print("  (Deixe em branco para usar o padrão: ./resultado.csv)")
    caminho_input = input("Digite o caminho completo ou deixe em branco: ").strip()

    if not caminho_input:
        return Path("resultado.csv").resolve()

    path = Path(caminho_input).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def exibir_resultado(
    df: pd.DataFrame, nomes_relatorios: list[str], modo: str = "nao_feitos"
) -> None:
    print(f"\nRelatórios processados: {', '.join(sorted(nomes_relatorios))}")
    print("-" * 80)

    if df.empty:
        print("\nNenhum aluno encontrado.")
        return

    if modo == "nao_feitos":
        col_relatorios = "relatorios_ausentes"
        col_total = "total_ausencias"
        header_col = "Relatórios Ausentes"
        mensagem_vazio = "—"
        mensagem_final = "aluno(s) com pelo menos 1 ausência"
    else:
        col_relatorios = "relatorios_feitos"
        col_total = "total_feitos"
        header_col = "Relatórios Feitos"
        mensagem_vazio = "Nenhum"
        mensagem_final = "aluno(s) com pelo menos 1 relatório feito"

    col_nome = max(df["nome_completo"].str.len().max(), len("Nome Completo"))
    col_estado = max(df["estado"].str.len().max(), len("Estado"))
    col_empresa = max(df["empresa"].str.len().max(), len("Empresa"))
    col_relatorios_max = max(
        df[col_relatorios].str.len().max()
        if not df[col_relatorios].eq("").all()
        else 0,
        len(header_col),
    )

    header = (
        f"{'Nome Completo':<{col_nome}}  "
        f"{'Estado':<{col_estado}}  "
        f"{'Empresa':<{col_empresa}}  "
        f"{header_col:<{col_relatorios_max}}  "
        f"Total"
    )
    print(f"\n{header}")
    print("-" * len(header))

    for _, row in df.iterrows():
        relatorios_text = row[col_relatorios] if row[col_relatorios] else mensagem_vazio
        print(
            f"{row['nome_completo']:<{col_nome}}  "
            f"{row['estado']:<{col_estado}}  "
            f"{row['empresa']:<{col_empresa}}  "
            f"{relatorios_text:<{col_relatorios_max}}  "
            f"{row[col_total]}"
        )

    com_ocorrencia = (df[col_total] > 0).sum()
    print(f"\nTotal: {len(df)} aluno(s) | {com_ocorrencia} {mensagem_final}.")


def salvar_resultado(df: pd.DataFrame, destino: Path, modo: str = "nao_feitos") -> None:
    if df.empty:
        print("Nenhum resultado encontrado. Arquivo de resultado não gerado.")
        return

    # Garante a criação da pasta pai (ex: /dados) antes de salvar
    destino.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(destino, index=False, encoding="utf-8-sig")
    print(f"Resultado salvo com sucesso em: {destino}")


def main(args_list: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Analisa presenças e ausências em relatórios de alunos.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--pasta-origem", "-d", type=str, default=None)
    parser.add_argument("--planilha", "-p", type=str, default=None)
    parser.add_argument(
        "--modo", "-m", type=str, choices=["feitos", "nao_feitos"], default=None
    )
    parser.add_argument("--output", "-o", type=str, default=None)

    # === CORREÇÃO CRÍTICA AQUI ===
    # Se args_list for passado via função, usamos ele. Se for None, o argparse olha o sys.argv.
    args = parser.parse_args(args_list)

    # === PASSO 1: Determinar pasta de input ===
    pasta_padrao = Path(".")
    if args.pasta_origem:
        diretorio = Path(args.pasta_origem).expanduser().resolve()
        if not diretorio.is_dir():
            print(f"ERRO: Pasta '{args.pasta_origem}' não encontrada ou inválida.")
            sys.exit(1)
    else:
        diretorio = selecionar_pasta_origem(pasta_padrao)

    # === PASSO 2: Determinar planilha geral ===
    if args.planilha:
        planilha_geral = resolver_arquivo_csv(args.planilha, Path.cwd())
    else:
        csvs = listar_csvs(diretorio)
        planilha_geral = selecionar_planilha_geral(csvs)

    print(f"\nCarregando planilha geral: {planilha_geral.name}")
    df_alunos = carregar_alunos(planilha_geral)
    print(f"  {len(df_alunos)} aluno(s) encontrado(s).")

    # === PASSO 3: Determinar relatórios ===
    if not args.planilha:
        csvs = listar_csvs(diretorio)
    else:
        csvs = list(diretorio.glob("*.csv"))

    # Filtra mantendo apenas os relatórios reais
    relatorios_paths = [p for p in csvs if p.resolve() != planilha_geral.resolve()]

    relatorios: dict[str, set[str]] = {}
    for path in relatorios_paths:
        respondentes = carregar_relatorio(path)
        if respondentes or "Nome completo" in pd.read_csv(path, nrows=0).columns:
            relatorios[path.stem] = respondentes

    # === PASSO 4: Determinar modo de visualização ===
    modo = args.modo if args.modo else selecionar_modo()

    if modo == "nao_feitos":
        df_resultado = calcular_ausencias(df_alunos, relatorios)
    else:
        df_resultado = calcular_presencas(df_alunos, relatorios)

    exibir_resultado(df_resultado, list(relatorios.keys()), modo)

    # === PASSO 5: Determinar caminho de saída e Salvar ===
    if args.output:
        caminho_output = Path(args.output).resolve()
    else:
        caminho_output = selecionar_caminho_output(diretorio)

    salvar_resultado(df_resultado, caminho_output, modo)


if __name__ == "__main__":
    main()
