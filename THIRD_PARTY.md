# Sources and attribution

- The connectome importer, inferred visual projection, spiking kernel and baseline-centered plasticity implementation are adapted from [DOOMFLY](https://github.com/nftechie/doomfly), copyright © 2026 nftechie and DOOMFLY contributors, under the MIT License preserved in `LICENSE`. Stonkfly adds the trading environment, execution guard, AgentKit bridge and the explicit two-compartment extension. No Doom game assets, World Labs assets, movie clips or portfolio material are included.
- [MaleCNS v1.0](https://male-cns.janelia.org/) data: the MaleCNS collaboration and upstream contributors, distributed under the release’s Creative Commons Attribution 4.0 terms. Downloaded separately; see `stonkfly/neural/datasets.json` and `sources.lock.json` for release URLs and checksums. Cite the dataset and its associated paper when publishing results. Stonkfly’s retained graph and modeled physiology are derived interpretations, not an official dataset product.
- [Coinbase AgentKit](https://github.com/coinbase/agentkit) (Apache-2.0) and [Coinbase Advanced Python SDK](https://github.com/coinbase/coinbase-advanced-py) (Apache-2.0) are installed dependencies. Their licenses remain with their packages. This project is not an official Coinbase product or endorsement.
- Scientific sources informing the model are linked in `docs/model.md`. No papers or figures are redistributed.
- `assets/stonkfly.png` is newly generated project artwork; its generation prompt is in `assets/image-generation.md`.

## 초파리 트레이딩 챌린지 (this fork)

- Dashboard base: [Bgihe/stonkfly-dashboard](https://github.com/Bgihe/stonkfly-dashboard), MIT (see `LICENSE`); its original README is `docs/bgihe-dashboard-README.md`.
- 3D fly character and desk layout in `dashboard/room/fly.js` and `dashboard/room/studio.js` are ported from [Degeneret Fly](https://github.com/Rob-bio4/degeneretfly), Copyright (c) 2026 Robillionair OÜ, MIT — licence text in `dashboard/room/LICENSE-degeneretfly.txt`.
- [three.js](https://threejs.org/) r180 is vendored under `dashboard/room/vendor/`, MIT — `dashboard/room/vendor/LICENSE-three.txt`.
- [Pretendard](https://github.com/orioncactus/pretendard) (subset, `dashboard/assets/fonts/`), SIL Open Font License 1.1 — `dashboard/assets/fonts/LICENSE-Pretendard.txt`.
- Market data: OrangeX public API (BTC-USDT-PERPETUAL quotes and funding) and Bybit public 1-minute candles for the initial chart. Only public endpoints are used; no account or key. Not affiliated with or endorsed by either exchange.
- The web viewer (`ops/site/`) redistributes neuron positions derived from MaleCNS v1.0 (CC BY 4.0) with the attribution shown on every page.
