import fs from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

/**
 * PARIDADE DO TEMPLATE COOLIFY COM O PROD — vigiado por máquina.
 *
 * ─── Por que este arquivo existe ─────────────────────────────────────────────
 *
 * O template `docker-compose.coolify.yml` é um fork congelado do
 * `docker-compose.prod.yml` com transformações fixas (sem Caddy, sem TCP
 * publicado, sem roteamento Traefik). Sem gate, qualquer mudança no `prod`
 * (pin novo, healthcheck, serviço) apodrece o template em silêncio — e a
 * primeira prova seria um deploy Coolify quebrado no cliente.
 *
 * O `portas-do-compose.test.ts` cobre `prod` + `traefik` e EXCLUI este
 * template de propósito (escopo dele). Este arquivo é o espelho: vigia o
 * template contra o `prod`, na mesma técnica (parsing de string, sem
 * dependência nova).
 */

const RAIZ = process.cwd();
const PROD = "docker-compose.prod.yml";
const TEMPLATE = ".agents/skills/deskcomm-instalar/templates/docker-compose.coolify.yml";

/**
 * Parser dos blocos de serviço, no molde de
 * `tests/unit/portas-do-compose.test.ts`. Não é um parser de YAML: é o
 * suficiente para responder "este serviço declara X?" sem trazer uma
 * dependência nova para um gate.
 */
function lerServicos(yaml: string): Map<string, string> {
  const linhas = yaml.split("\n");
  const servicos = new Map<string, string>();
  let dentroDeServices = false;
  let atual: string | null = null;
  let buffer: string[] = [];

  const fechar = () => {
    if (atual) servicos.set(atual, buffer.join("\n"));
    atual = null;
    buffer = [];
  };

  for (const linha of linhas) {
    if (/^services:\s*$/.test(linha)) {
      dentroDeServices = true;
      continue;
    }
    if (!dentroDeServices) continue;
    if (/^\S/.test(linha) && linha.trim() !== "") {
      fechar();
      dentroDeServices = false;
      continue;
    }
    const cabecalho = linha.match(/^ {2}([a-z0-9_-]+):\s*$/i);
    if (cabecalho) {
      fechar();
      atual = cabecalho[1] ?? null;
      continue;
    }
    if (atual) buffer.push(linha);
  }
  fechar();
  return servicos;
}

/**
 * O compose CITA portas e comandos em comentário para explicá-los. Sem esta
 * limpeza o regex acusaria a prosa — e um gate que acusa o inocente é
 * desligado por quem o herdar.
 */
function semComentarios(bloco: string): string {
  return bloco
    .split("\n")
    .filter((l) => !/^\s*#/.test(l))
    .join("\n");
}

/** Tira o comentário de fim de linha (`  # ...`) para comparar só código. */
function semComentarioInline(linha: string): string {
  return linha.replace(/\s+#.*$/, "").trimEnd();
}

const prod = fs.readFileSync(path.join(RAIZ, PROD), "utf8");
const template = fs.readFileSync(path.join(RAIZ, TEMPLATE), "utf8");
const SERVICOS_PROD = lerServicos(prod);
const SERVICOS_TEMPLATE = lerServicos(template);

describe("paridade do template coolify com o prod", () => {
  it("o parser enxerga os serviços esperados nos dois arquivos", () => {
    // GUARDA DO INSTRUMENTO. Sem esta asserção, um parser quebrado deixaria
    // todos os casos abaixo verdes por não terem medido nada — que é a forma
    // mais silenciosa de um gate morrer.
    expect([...SERVICOS_PROD.keys()].sort()).toEqual(
      ["app", "caddy", "redis", "scheduler", "srh", "wacalls", "waha", "worker"].sort(),
    );
    expect([...SERVICOS_TEMPLATE.keys()].sort()).toEqual(
      ["app", "redis", "scheduler", "srh", "wacalls", "waha", "worker"].sort(),
    );
  });

  it("o template tem os serviços do prod menos o caddy", () => {
    // Derivação fixa nº 1: o Caddy compete com o Traefik do Coolify nas
    // portas 80/443, então o bloco `caddy:` sai — e SÓ ele sai. Se o `prod`
    // ganhar um serviço e o template não acompanhar, este caso quebra e
    // aponta o nome.
    const doProd = [...SERVICOS_PROD.keys()].filter((s) => s !== "caddy").sort();
    const doTemplate = [...SERVICOS_TEMPLATE.keys()].sort();
    expect(doTemplate).toEqual(doProd);
  });

  it("só o wacalls publica porta, só UDP, host == contêiner", () => {
    // Derivação fixa nº 2: o template não publica TCP (o TLS termina no
    // Traefik do Coolify). A exceção é o UDP do WebRTC — mesma exceção do
    // `portas-do-compose.test.ts`, com a mesma razão: o áudio não fala HTTP,
    // então não há proxy que o carregue.
    const publicando: string[] = [];

    for (const [nome, bloco] of SERVICOS_TEMPLATE) {
      const limpo = semComentarios(bloco);
      if (!/^\s{4}ports:/m.test(limpo)) continue;
      if (nome !== "wacalls") {
        publicando.push(nome);
        continue;
      }
      const trecho = /^\s{4}ports:\s*$\n((?:\s{6}-.*\n)+)/m.exec(limpo)?.[1] ?? "";
      const linhas = [...trecho.matchAll(/^\s{6}-\s*"?([^"\n]+)"?\s*$/gm)]
        .map((m) => m[1]!.trim())
        .map((l) => l.replace(/\$\{[^}]*:-([^}]*)\}/g, "$1"));
      for (const linha of linhas) {
        if (!linha.endsWith("/udp")) {
          publicando.push(`${nome}: "${linha}" não é /udp`);
          continue;
        }
        const [host, resto] = linha.split(":");
        const contentor = (resto ?? "").replace("/udp", "");
        if (host !== contentor) {
          publicando.push(`${nome}: "${linha}" remapeia (host ≠ contêiner)`);
        }
      }
    }

    expect(
      publicando,
      `publicando porta fora da exceção UDP do wacalls: ${publicando.join(", ")}.`,
    ).toEqual([]);
  });

  it("nenhum serviço do template tem label de roteamento traefik", () => {
    // O FQDN vive no painel do Coolify (Domains), não neste arquivo. Label
    // `traefik.enable` aqui seria exposição à internet que o teste de
    // `ports:` não enxerga.
    const roteados = [...SERVICOS_TEMPLATE.entries()]
      .filter(([, b]) => /traefik\.enable/.test(semComentarios(b)))
      .map(([nome]) => nome);

    expect(roteados, `serviço com label traefik: ${roteados.join(", ")}.`).toEqual([]);
  });

  it("nenhum serviço do template usa network_mode: host", () => {
    // A porta dos fundos da regra de `ports:`: dispensa o mapeamento e expõe
    // TUDO que o processo escutar.
    const emHost = [...SERVICOS_TEMPLATE.entries()]
      .filter(([, b]) => /^\s{4}network_mode:\s*["']?host/m.test(semComentarios(b)))
      .map(([nome]) => nome);

    expect(emHost, `serviço em network_mode: host: ${emHost.join(", ")}.`).toEqual([]);
  });

  it("só o redis tem command:, e é a linha exata do prod", () => {
    // O `command:` do redis é tuning de cache (força efêmero: sem RDB, sem
    // AOF), não override de boot — por isso ele fica, VERBATIM do `prod`.
    // Qualquer outro `command:` seria um override de boot contrabandeado.
    const comCommand = [...SERVICOS_TEMPLATE.entries()]
      .filter(([, b]) => /^\s{4}command:/m.test(semComentarios(b)))
      .map(([nome]) => nome);

    expect(
      comCommand.sort(),
      `command: fora do redis: ${comCommand.join(", ")}. Só o redis pode — e com a linha exata do ${PROD}.`,
    ).toEqual(["redis"]);

    const linhaProd = (SERVICOS_PROD.get("redis") ?? "")
      .split("\n")
      .filter((l) => /^\s{4}command:/.test(l))
      .map(semComentarioInline);
    const linhaTemplate = (SERVICOS_TEMPLATE.get("redis") ?? "")
      .split("\n")
      .filter((l) => /^\s{4}command:/.test(l))
      .map(semComentarioInline);

    expect(linhaProd, "o prod perdeu o command: do redis — a régua desta comparação está vazia").toHaveLength(1);
    expect(linhaTemplate).toEqual(linhaProd);
  });

  it("os volumes de sessão e mídia do WhatsApp persistem", () => {
    // Apagar `waha-data` desvincula o número (novo QR); apagar `waha-media`
    // perde a mídia. Os dois precisam estar declarados no template.
    const trechoVolumes = /^volumes:\s*$\n((?:  \S.*(?:\n|$))+)/m.exec(template)?.[1] ?? "";
    expect(trechoVolumes, "o template perdeu o bloco `volumes:`").not.toBe("");
    for (const volume of ["waha-data", "waha-media"]) {
      expect(
        new RegExp(`^  ${volume}:`, "m").test(trechoVolumes),
        `volume \`${volume}\` sumiu do template — redeploy no painel apagaria dado do WhatsApp.`,
      ).toBe(true);
    }
  });
});
