//! Anika Blue: vote on shades of blue until your personal blue emerges.

pub mod color;
mod css3;

use std::{
    hash::{DefaultHasher, Hash, Hasher},
    path::Path,
    sync::{Arc, Mutex, MutexGuard},
};

use axum::{
    Form, Json, Router,
    extract::{FromRef, Path as UrlPath, State},
    http::{HeaderValue, StatusCode, header},
    response::{Html, IntoResponse, Response},
    routing::{get, post},
};
use axum_extra::extract::cookie::{Cookie, Key, SameSite, SignedCookieJar};
use minijinja::{Environment, Value, context, value::Serde};
use rusqlite::{Connection, OptionalExtension, params};
use serde::{Deserialize, Serialize};
use serde_json::json;
use sha2::{Digest, Sha512};
use tower_http::compression::CompressionLayer;

use crate::color::{ColorDetails, Rgb};

const SESSION_COOKIE: &str = "anika_blue_uid";

const STATIC_FILES: &[(&str, &str, &str)] = &[
    (
        "app.css",
        "text/css; charset=utf-8",
        include_str!("../static/app.css"),
    ),
    (
        "app.js",
        "text/javascript; charset=utf-8",
        include_str!("../static/app.js"),
    ),
];

/// Running RGB sums of all "yes" votes, so the global average costs O(1).
#[derive(Default)]
struct Totals {
    r: u64,
    g: u64,
    b: u64,
    count: u64,
}

impl Totals {
    fn add(&mut self, color: Rgb) {
        self.r += u64::from(color.0);
        self.g += u64::from(color.1);
        self.b += u64::from(color.2);
        self.count += 1;
    }

    fn average(&self) -> Option<Average> {
        Average::from_sums(self.r, self.g, self.b, self.count)
    }
}

/// The mean of a set of votes (channels truncated, like the original app).
struct Average {
    color: Rgb,
    count: u64,
}

impl Average {
    fn from_sums(r: u64, g: u64, b: u64, count: u64) -> Option<Self> {
        let mean = |sum: u64| u8::try_from(sum / count).unwrap_or(u8::MAX);
        (count > 0).then(|| Self {
            color: Rgb(mean(r), mean(g), mean(b)),
            count,
        })
    }
}

#[derive(Serialize)]
struct AverageView {
    #[serde(flatten)]
    details: ColorDetails,
    count: u64,
}

impl From<Average> for AverageView {
    fn from(avg: Average) -> Self {
        Self {
            details: ColorDetails::new(avg.color),
            count: avg.count,
        }
    }
}

struct Inner {
    db: Mutex<Connection>,
    totals: Mutex<Totals>,
    templates: Environment<'static>,
    asset_version: String,
}

/// Shared application state.
#[derive(Clone)]
pub struct AppState {
    inner: Arc<Inner>,
    key: Key,
}

impl FromRef<AppState> for Key {
    fn from_ref(state: &AppState) -> Self {
        state.key.clone()
    }
}

impl AppState {
    /// Open (and migrate) the database at `database` and sign cookies with `secret`.
    ///
    /// Without a secret, a random key is used and sessions end on restart.
    pub fn new(database: &Path, secret: Option<&[u8]>) -> anyhow::Result<Self> {
        let conn = Connection::open(database)?;
        init_db(&conn)?;
        let totals = load_totals(&conn)?;

        let mut templates = Environment::new();
        templates.add_template("index.html", include_str!("../templates/index.html"))?;
        templates.add_template(
            "shade_card.html",
            include_str!("../templates/shade_card.html"),
        )?;
        templates.add_template("stats.html", include_str!("../templates/stats.html"))?;

        let mut hasher = DefaultHasher::new();
        STATIC_FILES.hash(&mut hasher);

        Ok(Self {
            inner: Arc::new(Inner {
                db: Mutex::new(conn),
                totals: Mutex::new(totals),
                templates,
                asset_version: format!("{:x}", hasher.finish()),
            }),
            key: secret.map_or_else(Key::generate, |s| Key::from(&Sha512::digest(s))),
        })
    }

    fn db(&self) -> MutexGuard<'_, Connection> {
        self.inner
            .db
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
    }

    fn totals(&self) -> MutexGuard<'_, Totals> {
        self.inner
            .totals
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
    }

    fn render(&self, name: &str, ctx: Value) -> Result<Html<String>, AppError> {
        let ctx = context! { asset_version => &self.inner.asset_version, ..ctx };
        Ok(Html(self.inner.templates.get_template(name)?.render(ctx)?))
    }

    fn new_shade(&self, user_id: &str) -> Result<Rgb, AppError> {
        let shade = Rgb::random_blue();
        self.db().execute(
            "INSERT INTO shown_shades (user_id, hex_color) VALUES (?1, ?2)",
            params![user_id, shade.hex()],
        )?;
        Ok(shade)
    }

    fn user_average(&self, user_id: &str) -> Result<Option<Average>, AppError> {
        let db = self.db();
        let mut stmt = db.prepare_cached(
            "SELECT hex_color FROM votes WHERE user_id = ?1 AND is_anika_blue = 1",
        )?;
        let mut totals = Totals::default();
        for hex in stmt.query_map([user_id], |row| row.get::<_, String>(0))? {
            if let Some(color) = Rgb::parse(&hex?) {
                totals.add(color);
            }
        }
        Ok(totals.average())
    }

    fn stats_context(&self, user_id: &str) -> Result<Value, AppError> {
        let user_avg = self.user_average(user_id)?.map(AverageView::from);
        let global_avg = self.totals().average().map(AverageView::from);
        Ok(context! {
            user_avg => Serde(user_avg),
            global_avg => Serde(global_avg),
        })
    }
}

fn init_db(conn: &Connection) -> rusqlite::Result<()> {
    conn.pragma_update(None, "journal_mode", "WAL")?;
    conn.pragma_update(None, "synchronous", "NORMAL")?;

    // Migrate the legacy "choices" table.
    let has = |name: &str| -> rusqlite::Result<bool> {
        conn.query_row(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?1",
            [name],
            |_| Ok(()),
        )
        .optional()
        .map(|row| row.is_some())
    };
    if !has("votes")? && has("choices")? {
        conn.execute("ALTER TABLE choices RENAME TO votes", [])?;
    }

    conn.execute_batch(
        "CREATE TABLE IF NOT EXISTS votes (
             id INTEGER PRIMARY KEY AUTOINCREMENT,
             user_id TEXT NOT NULL,
             hex_color TEXT NOT NULL,
             is_anika_blue INTEGER NOT NULL,
             timestamp DATETIME DEFAULT CURRENT_TIMESTAMP);
         CREATE TABLE IF NOT EXISTS shown_shades (
             id INTEGER PRIMARY KEY AUTOINCREMENT,
             user_id TEXT NOT NULL,
             hex_color TEXT NOT NULL,
             timestamp DATETIME DEFAULT CURRENT_TIMESTAMP);
         CREATE TABLE IF NOT EXISTS user_base_colors (
             user_id TEXT PRIMARY KEY,
             base_color TEXT NOT NULL,
             timestamp DATETIME DEFAULT CURRENT_TIMESTAMP);
         CREATE INDEX IF NOT EXISTS idx_votes_user ON votes (user_id, is_anika_blue);
         CREATE INDEX IF NOT EXISTS idx_user_base_colors_color ON user_base_colors (base_color);",
    )
}

fn load_totals(conn: &Connection) -> rusqlite::Result<Totals> {
    let mut stmt = conn.prepare("SELECT hex_color FROM votes WHERE is_anika_blue = 1")?;
    let mut totals = Totals::default();
    for hex in stmt.query_map([], |row| row.get::<_, String>(0))? {
        if let Some(color) = Rgb::parse(&hex?) {
            totals.add(color);
        }
    }
    Ok(totals)
}

/// Build the HTTP router.
pub fn router(state: AppState) -> Router {
    Router::new()
        .route("/", get(index))
        .route("/next-shade", get(next_shade))
        .route("/vote", post(vote))
        .route("/stats", get(stats))
        .route("/save-base-color", post(save_base_color))
        .route("/load-base-color", post(load_base_color))
        .route("/favicon.ico", get(favicon))
        .route("/static/{file}", get(static_file))
        .route("/healthz", get(|| async { "ok" }))
        .layer(CompressionLayer::new())
        .with_state(state)
}

// --- Sessions -----------------------------------------------------------------

/// Return the visitor's id, creating a session cookie when there is none.
fn session(jar: SignedCookieJar) -> (SignedCookieJar, String) {
    if let Some(cookie) = jar.get(SESSION_COOKIE) {
        let id = cookie.value().to_owned();
        return (jar, id);
    }
    let id = new_user_id();
    (jar.add(session_cookie(id.clone())), id)
}

fn new_user_id() -> String {
    rand::random::<[u8; 16]>()
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}

fn session_cookie(user_id: String) -> Cookie<'static> {
    Cookie::build((SESSION_COOKIE, user_id))
        .path("/")
        .http_only(true)
        .same_site(SameSite::Lax)
        .permanent()
        .build()
}

// --- Handlers -----------------------------------------------------------------

async fn index(State(state): State<AppState>, jar: SignedCookieJar) -> Result<Response, AppError> {
    let (jar, user_id) = session(jar);
    let shade = state.new_shade(&user_id)?;
    let ctx = context! {
        shade => shade.hex(),
        shade_details => Serde(ColorDetails::new(shade)),
        ..state.stats_context(&user_id)?
    };
    let mut response = (jar, state.render("index.html", ctx)?).into_response();
    response
        .headers_mut()
        .insert(header::CACHE_CONTROL, HeaderValue::from_static("no-store"));
    Ok(response)
}

async fn next_shade(
    State(state): State<AppState>,
    jar: SignedCookieJar,
) -> Result<impl IntoResponse, AppError> {
    let (jar, user_id) = session(jar);
    let shade = state.new_shade(&user_id)?;
    let html = state.render(
        "shade_card.html",
        context! {
            shade => shade.hex(),
            shade_details => Serde(ColorDetails::new(shade)),
        },
    )?;
    Ok((jar, html))
}

#[derive(Deserialize)]
struct VoteForm {
    shade: Option<String>,
    vote: Option<String>,
    /// Legacy name of `vote`.
    choice: Option<String>,
}

async fn vote(
    State(state): State<AppState>,
    jar: SignedCookieJar,
    Form(form): Form<VoteForm>,
) -> Result<Response, AppError> {
    let (jar, user_id) = session(jar);
    let is_anika_blue = match form.vote.or(form.choice).as_deref() {
        Some("yes") => Some(true),
        Some("no") => Some(false),
        Some("skip") => None,
        _ => return Ok(json_error(StatusCode::BAD_REQUEST, "Invalid vote")),
    };

    if let Some(is_anika_blue) = is_anika_blue {
        let Some(shade) = form.shade.as_deref().and_then(Rgb::parse) else {
            return Ok(json_error(StatusCode::BAD_REQUEST, "Invalid shade"));
        };
        state.db().execute(
            "INSERT INTO votes (user_id, hex_color, is_anika_blue) VALUES (?1, ?2, ?3)",
            params![user_id, shade.hex(), is_anika_blue],
        )?;
        if is_anika_blue {
            state.totals().add(shade);
        }
    }

    if let Some(avg) = state.user_average(&user_id)? {
        set_base_color(&state, &user_id, avg.color)?;
    }

    let html = state.render("stats.html", state.stats_context(&user_id)?)?;
    Ok((jar, html).into_response())
}

async fn stats(
    State(state): State<AppState>,
    jar: SignedCookieJar,
) -> Result<impl IntoResponse, AppError> {
    let (jar, user_id) = session(jar);
    let html = state.render("stats.html", state.stats_context(&user_id)?)?;
    Ok((jar, html))
}

fn set_base_color(state: &AppState, user_id: &str, color: Rgb) -> rusqlite::Result<usize> {
    state.db().execute(
        "INSERT OR REPLACE INTO user_base_colors (user_id, base_color) VALUES (?1, ?2)",
        params![user_id, color.hex()],
    )
}

async fn save_base_color(
    State(state): State<AppState>,
    jar: SignedCookieJar,
) -> Result<Response, AppError> {
    let (jar, user_id) = session(jar);
    let Some(avg) = state.user_average(&user_id)? else {
        return Ok(json_error(
            StatusCode::BAD_REQUEST,
            "No average color available",
        ));
    };
    set_base_color(&state, &user_id, avg.color)?;
    Ok((
        jar,
        Json(json!({ "success": true, "base_color": avg.color.hex() })),
    )
        .into_response())
}

#[derive(Deserialize)]
struct BaseColorForm {
    #[serde(default)]
    base_color: String,
}

async fn load_base_color(
    State(state): State<AppState>,
    jar: SignedCookieJar,
    Form(form): Form<BaseColorForm>,
) -> Result<Response, AppError> {
    if form.base_color.trim().is_empty() {
        return Ok(json_error(
            StatusCode::BAD_REQUEST,
            "No base color provided",
        ));
    }
    let Some(color) = Rgb::parse(&form.base_color) else {
        return Ok(json_error(
            StatusCode::BAD_REQUEST,
            "Invalid hex color format",
        ));
    };

    let user_id: Option<String> = state
        .db()
        .query_row(
            "SELECT user_id FROM user_base_colors WHERE base_color = ?1",
            [color.hex()],
            |row| row.get(0),
        )
        .optional()?;

    Ok(match user_id {
        Some(user_id) => (
            jar.add(session_cookie(user_id)),
            Json(json!({ "success": true, "message": "Session restored successfully" })),
        )
            .into_response(),
        None => json_error(StatusCode::NOT_FOUND, "No user found with this base color"),
    })
}

async fn favicon(
    State(state): State<AppState>,
    jar: SignedCookieJar,
) -> Result<Response, AppError> {
    let user = match jar.get(SESSION_COOKIE) {
        Some(cookie) => state.user_average(cookie.value())?,
        None => None,
    };
    let color = user
        .or_else(|| state.totals().average())
        .map_or(Rgb(0x66, 0x7e, 0xea), |avg| avg.color);

    Ok((
        [
            (header::CONTENT_TYPE, "image/x-icon"),
            (header::CACHE_CONTROL, "no-cache"),
        ],
        ico(color),
    )
        .into_response())
}

/// A 32x32 single-color ICO with a 32-bit BMP payload.
fn ico(Rgb(r, g, b): Rgb) -> Vec<u8> {
    const SIZE: u32 = 32;
    const PIXELS: u32 = SIZE * SIZE * 4;
    const MASK: u32 = SIZE * SIZE / 8;
    const HEADER: u32 = 40;
    let mut out = Vec::with_capacity(22 + (HEADER + PIXELS + MASK) as usize);
    // ICONDIR
    out.extend_from_slice(&[0, 0, 1, 0, 1, 0]);
    // ICONDIRENTRY
    out.extend_from_slice(&[32, 32, 0, 0, 1, 0, 32, 0]);
    out.extend_from_slice(&(HEADER + PIXELS + MASK).to_le_bytes());
    out.extend_from_slice(&22u32.to_le_bytes());
    // BITMAPINFOHEADER (height covers XOR + AND masks)
    out.extend_from_slice(&HEADER.to_le_bytes());
    out.extend_from_slice(&SIZE.to_le_bytes());
    out.extend_from_slice(&(SIZE * 2).to_le_bytes());
    out.extend_from_slice(&1u16.to_le_bytes());
    out.extend_from_slice(&32u16.to_le_bytes());
    out.extend_from_slice(&[0; 24]);
    for _ in 0..SIZE * SIZE {
        out.extend_from_slice(&[b, g, r, 255]);
    }
    out.resize(out.len() + MASK as usize, 0);
    out
}

async fn static_file(UrlPath(file): UrlPath<String>) -> Response {
    STATIC_FILES
        .iter()
        .find(|(name, ..)| *name == file)
        .map_or_else(
            || StatusCode::NOT_FOUND.into_response(),
            |(_, mime, body)| {
                (
                    [
                        (header::CONTENT_TYPE, *mime),
                        // URLs carry the asset hash, so they never change.
                        (header::CACHE_CONTROL, "public, max-age=31536000, immutable"),
                    ],
                    *body,
                )
                    .into_response()
            },
        )
}

// --- Errors -------------------------------------------------------------------

fn json_error(status: StatusCode, error: &str) -> Response {
    (status, Json(json!({ "success": false, "error": error }))).into_response()
}

/// Internal errors are logged and reported as a plain 500.
#[derive(Debug, thiserror::Error)]
enum AppError {
    #[error(transparent)]
    Db(#[from] rusqlite::Error),
    #[error(transparent)]
    Template(#[from] minijinja::Error),
}

impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        tracing::error!("{self}");
        (StatusCode::INTERNAL_SERVER_ERROR, "Internal Server Error").into_response()
    }
}
