#!/bin/bash
# Extrator Caramujo: move downloads das subpastas de Downloads pras pastas finais.
# Disparado pelo launchd toda vez que algo muda em Downloads/Samples ou Downloads/Inspiracoes.

# Dá um respiro pro Chrome terminar de renomear o arquivo
sleep 2

mover() {
  local origem="$1" destino="$2"
  [ -d "$origem" ] || return 0
  mkdir -p "$destino"

  for f in "$origem"/*; do
    [ -f "$f" ] || continue
    # Ignora download em andamento
    case "$f" in
      *.crdownload|*.download|*.part|*.tmp) continue ;;
    esac

    local base alvo nome ext
    base="$(basename "$f")"
    alvo="$destino/$base"

    # Se já existe arquivo com esse nome no destino, acrescenta a hora
    if [ -e "$alvo" ]; then
      nome="${base%.*}"
      ext="${base##*.}"
      alvo="$destino/$nome $(date +%H%M%S).$ext"
    fi

    mv "$f" "$alvo"
  done
}

mover "$HOME/Downloads/Samples"     "$HOME/Music/@rideblan33/Samples"
mover "$HOME/Downloads/Inspiracoes" "$HOME/Music/@rideblan33/Inspiration"
