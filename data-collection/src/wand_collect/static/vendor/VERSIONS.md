# Vendored files

These files are copied unchanged from the npm packages, at exact versions,
so the application needs no network and no build step. The source map
comments at the end of the Preact files point to files that are not included;
they only matter to browser developer tools.

| File | Package | Version | Source | SHA-256 |
|---|---|---|---|---|
| `preact.module.js` | preact | 10.24.3 | https://cdn.jsdelivr.net/npm/preact@10.24.3/dist/preact.module.js | `9ba8bb591b0c9a72132ff65a76e69c5a4e49cf71721b47b659f3243658bde05b` |
| `hooks.module.js` | preact (hooks) | 10.24.3 | https://cdn.jsdelivr.net/npm/preact@10.24.3/hooks/dist/hooks.module.js | `896fc8e546b96c3fca29743b493293820ad4e76396fd36ff05f18a52eaf303e1` |
| `htm.module.js` | htm | 3.1.1 | https://cdn.jsdelivr.net/npm/htm@3.1.1/dist/htm.module.js | `ab33dd3f38059b9be4d5f5350128eefb2356639c4e0bbe9d9e8b3ba75847e9e4` |

`hooks.module.js` imports the bare name `preact`; `index.html` maps it to
`preact.module.js` with an import map.

To update a file, download the new version, replace the file, and update this
table (version, URL and checksum) in the same change.
