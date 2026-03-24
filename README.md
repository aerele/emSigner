### emSigner

Integrating emSigner (eMudhra) with ERPNext. Electronically or digitally sign documents such as Invoices or Purchase Orders using legally valid digital signature certificates or Aadhaar OTP authentication — with just a couple of clicks.

Enable any DocType for e-signatures, configure authorized signatories, and invite external parties to sign — all from a single settings page.

### Features

- **Sign Any DocType** — Enable signing on any document type (Sales Invoice, Purchase Order, etc.) from emSigner Settings.
- **Multiple Signature Modes** — Aadhaar eSign, Digital Signature (crypto token), eMudhra KYC eSign, and eSign v3.
- **Authentication Options** — OTP, Biometric, Iris, and Face authentication.
- **External Signatory Support** — Invite non-system users to sign documents via secure email links (JWT-authenticated, no ERPNext login required).
- **Post-Submission Signing** — Sign documents even after they have been submitted.
- **Interactive Signature Placement** — Full PDF preview with drag-and-drop signature positioning, 9 preset positions, or custom coordinates.
- **Pre-Sign Preview** — Visualize all pending signatures on the document before initiating the signing flow.
- **Signing Progress Tracking** — Contextual status banner on document forms with per-signatory progress, status dialog, and individual resend buttons.
- **Overlap & Page Warnings** — Automatic detection of overlapping signatures and out-of-range page numbers.
- **Button-Driven Setup** — Guided configuration via Setup Doctype, Add Signatory, Reposition, and Reset buttons in settings.

### How It Works

1. **Configure** — Set up credentials, gateway URL, signature mode, and authentication in emSigner Settings.
2. **Enable DocTypes** — Add document types to the signing whitelist and assign print formats.
3. **Add Signatories** — Configure authorized system users or add external signatories per DocType.
4. **Place Signatures** — Use the interactive PDF viewer to position signatures (preset or custom coordinates).
5. **Request Signatures** — Click "Request Signature" on any enabled document to email secure signing links to all pending signatories.
6. **Sign** — Signatories click the link, review the document, and sign via the eMudhra gateway.
7. **Track** — Monitor signing progress via the status banner and dialog on the document form.

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench --site <site-name> install-app emsigner
```

### Dependencies

- [Frappe Framework](https://github.com/frappe/frappe) v15+
- [pycryptodome](https://pypi.org/project/pycryptodome/) — AES/RSA encryption
- [PyJWT](https://pypi.org/project/PyJWT/) — Token-based authentication for external signatories

### Demo



https://github.com/user-attachments/assets/dc97d616-f190-4f2b-8139-17a389140aeb



### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/emsigner
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

MIT
