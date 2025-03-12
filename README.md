### emSigner

Integrating emSigner in ERPNext. Electronically or digitally sign documents such as Invoices or Purchase orders using legally valid digital signature certificates or an Aadhar OTP with a couple of clicks. 

Enable any doctype for e-signatures from the authorised signatories from the settings.

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench --site <site-name> install-app emsigner
```

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

mit
