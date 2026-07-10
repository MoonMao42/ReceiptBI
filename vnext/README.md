# QueryGPT vNext

QueryGPT vNext is a clean-room, local-only analytics workspace for macOS and Windows.

This directory is intentionally independent from the previous application:

- no imports from the previous application;
- no copied pages, components, CSS, design tokens, contracts, or compatibility shell;
- no cloud execution path or remote sandbox provider;
- no Python process installed or launched on the host;
- no handwritten filesystem separator concatenation.

The first executable slice is deliberately small: a Rust semantic core exposed through N-API, a typed TypeScript boundary, a Result-First Workspace shell, and a macOS/Windows CI matrix.

This is **not yet the finished desktop product**. P0 remains in progress until the Electron host exists and the three native CI jobs have passed on their real target runners. See [`docs/STATUS.md`](docs/STATUS.md) for the current evidence and the next gate.

## Commands

```text
pnpm install
pnpm check
pnpm build:native
pnpm build:workspace
```

Product and architecture decisions live in [`docs/`](docs/).
