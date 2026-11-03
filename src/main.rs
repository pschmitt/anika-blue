use std::{net::SocketAddr, path::PathBuf};

use anyhow::Context;
use clap::{Parser, Subcommand};
use tracing_subscriber::EnvFilter;

/// Find your perfect shade of blue.
#[derive(Parser)]
#[command(version, about)]
struct Args {
    /// Address to listen on.
    #[arg(long, env = "BIND_HOST", default_value = "0.0.0.0")]
    host: String,

    /// Port to listen on.
    #[arg(long, env = "BIND_PORT", default_value_t = 5000, global = true)]
    port: u16,

    /// SQLite database file.
    #[arg(long, env = "DATABASE", default_value = "anika_blue.db")]
    database: PathBuf,

    /// Secret used to sign session cookies. Random (sessions reset on restart) if unset.
    #[arg(long, env = "SECRET_KEY", hide_env_values = true)]
    secret_key: Option<String>,

    /// File containing the cookie secret; overrides --secret-key.
    #[arg(long, env = "SECRET_KEY_FILE")]
    secret_key_file: Option<PathBuf>,

    #[command(subcommand)]
    command: Option<Command>,
}

#[derive(Subcommand)]
enum Command {
    /// Exit 0 when the server on --port answers /healthz (for container health checks).
    Healthcheck,
}

fn healthcheck(port: u16) -> anyhow::Result<()> {
    use std::{
        io::{Read, Write},
        net::TcpStream,
        time::Duration,
    };
    let mut stream = TcpStream::connect(("127.0.0.1", port))?;
    stream.set_read_timeout(Some(Duration::from_secs(2)))?;
    stream.write_all(b"GET /healthz HTTP/1.0\r\nHost: localhost\r\n\r\n")?;
    let mut response = String::new();
    stream.read_to_string(&mut response)?;
    anyhow::ensure!(
        response.starts_with("HTTP/1.0 200") || response.starts_with("HTTP/1.1 200"),
        "unhealthy: {}",
        response.lines().next().unwrap_or_default()
    );
    Ok(())
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(
            EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info")),
        )
        .init();

    let args = Args::parse();
    if matches!(args.command, Some(Command::Healthcheck)) {
        return healthcheck(args.port);
    }
    let secret = match &args.secret_key_file {
        Some(path) => Some(
            std::fs::read_to_string(path)
                .with_context(|| format!("reading {}", path.display()))?
                .trim()
                .to_owned(),
        ),
        None => args.secret_key.clone(),
    };
    if secret.is_none() {
        tracing::warn!("no SECRET_KEY set; sessions reset on every restart");
    }

    let state = anika_blue::AppState::new(&args.database, secret.as_deref().map(str::as_bytes))
        .with_context(|| format!("opening {}", args.database.display()))?;

    let addr: SocketAddr = format!("{}:{}", args.host, args.port)
        .parse()
        .context("invalid listen address")?;
    let listener = tokio::net::TcpListener::bind(addr).await?;
    tracing::info!("listening on http://{addr}");

    axum::serve(listener, anika_blue::router(state))
        .with_graceful_shutdown(async {
            let _ = tokio::signal::ctrl_c().await;
        })
        .await?;
    Ok(())
}
