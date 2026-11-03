use axum::{
    Router,
    body::Body,
    http::{Request, StatusCode, header},
};
use http_body_util::BodyExt;
use tempfile::TempDir;
use tower::ServiceExt;

struct TestApp {
    router: Router,
    cookie: Option<String>,
    _dir: TempDir,
}

struct Reply {
    status: StatusCode,
    content_type: String,
    body: String,
}

impl TestApp {
    fn new() -> Self {
        let dir = tempfile::tempdir().unwrap();
        let state = anika_blue::AppState::new(&dir.path().join("test.db"), Some(b"test")).unwrap();
        Self {
            router: anika_blue::router(state),
            cookie: None,
            _dir: dir,
        }
    }

    async fn send(&mut self, method: &str, uri: &str, form: Option<&str>) -> Reply {
        let mut req = Request::builder().method(method).uri(uri);
        if let Some(cookie) = &self.cookie {
            req = req.header(header::COOKIE, cookie);
        }
        let body = match form {
            Some(form) => {
                req = req.header(header::CONTENT_TYPE, "application/x-www-form-urlencoded");
                Body::from(form.to_owned())
            }
            None => Body::empty(),
        };
        let res = self
            .router
            .clone()
            .oneshot(req.body(body).unwrap())
            .await
            .unwrap();
        if let Some(set) = res.headers().get(header::SET_COOKIE) {
            let pair = set.to_str().unwrap().split(';').next().unwrap();
            self.cookie = Some(pair.to_owned());
        }
        let status = res.status();
        let content_type = res
            .headers()
            .get(header::CONTENT_TYPE)
            .map(|v| v.to_str().unwrap().to_owned())
            .unwrap_or_default();
        let bytes = res.into_body().collect().await.unwrap().to_bytes();
        Reply {
            status,
            content_type,
            body: String::from_utf8_lossy(&bytes).into_owned(),
        }
    }

    async fn get(&mut self, uri: &str) -> Reply {
        self.send("GET", uri, None).await
    }

    async fn post(&mut self, uri: &str, form: &str) -> Reply {
        self.send("POST", uri, Some(form)).await
    }
}

#[tokio::test]
async fn index_renders_shade_and_stats_inline() {
    let mut app = TestApp::new();
    let res = app.get("/").await;
    assert_eq!(res.status, StatusCode::OK);
    assert!(res.body.contains("class=\"swatch\""));
    assert!(res.body.contains("Your Anika Blue"));
    assert!(res.body.contains("/static/app.css?v="));
    assert!(app.cookie.is_some(), "session cookie is set");
}

#[tokio::test]
async fn next_shade_is_a_card() {
    let mut app = TestApp::new();
    let res = app.get("/next-shade").await;
    assert_eq!(res.status, StatusCode::OK);
    assert!(res.body.contains("data-shade=\"#"));
    assert!(res.body.contains("shade-name"));
    assert!(res.body.contains("data-shade-combined"));
    assert!(res.body.contains("data-copy-text"));
}

#[tokio::test]
async fn votes_update_personal_and_global_averages() {
    let mut app = TestApp::new();
    app.post("/vote", "shade=%230000ff&vote=yes").await;
    app.post("/vote", "shade=%2300ff00&vote=yes").await;
    let res = app.post("/vote", "shade=%23ff0000&vote=no").await;
    assert_eq!(res.status, StatusCode::OK);
    // (0+0)/2, (0+255)/2, (255+0)/2 -> #007f7f
    assert!(
        res.body.contains("data-user-color=\"#007f7f\""),
        "{}",
        res.body
    );
    assert!(res.body.contains("2 votes"));

    // Another visitor sees the same global average but no personal one.
    let mut other = TestApp {
        router: app.router.clone(),
        cookie: None,
        _dir: tempfile::tempdir().unwrap(),
    };
    let res = other.get("/stats").await;
    assert!(!res.body.contains("data-user-color"));
    assert!(res.body.contains("#007f7f"));
    assert!(res.body.contains("from everyone"));
}

#[tokio::test]
async fn skip_and_legacy_choice_are_accepted() {
    let mut app = TestApp::new();
    let res = app.post("/vote", "shade=%230000ff&vote=skip").await;
    assert_eq!(res.status, StatusCode::OK);
    let res = app.post("/vote", "shade=%230000ff&choice=yes").await;
    assert!(res.body.contains("data-user-color=\"#0000ff\""));
}

#[tokio::test]
async fn invalid_votes_are_rejected() {
    let mut app = TestApp::new();
    for form in [
        "shade=%230000ff&vote=maybe",
        "shade=nope&vote=yes",
        "vote=no",
    ] {
        let res = app.post("/vote", form).await;
        assert_eq!(res.status, StatusCode::BAD_REQUEST, "{form}");
    }
}

#[tokio::test]
async fn base_color_round_trip_restores_session() {
    let mut app = TestApp::new();
    let res = app.post("/save-base-color", "").await;
    assert_eq!(res.status, StatusCode::BAD_REQUEST);

    app.post("/vote", "shade=%231a2b3c&vote=yes").await;
    let res = app.post("/save-base-color", "").await;
    assert_eq!(res.status, StatusCode::OK);
    assert!(res.body.contains("\"base_color\":\"#1a2b3c\""));

    let mut other = TestApp {
        router: app.router.clone(),
        cookie: None,
        _dir: tempfile::tempdir().unwrap(),
    };
    let res = other.post("/load-base-color", "base_color=1A2B3C").await;
    assert_eq!(res.status, StatusCode::OK, "{}", res.body);
    let res = other.get("/stats").await;
    assert!(res.body.contains("data-user-color=\"#1a2b3c\""));
}

#[tokio::test]
async fn load_base_color_errors() {
    let mut app = TestApp::new();
    assert_eq!(
        app.post("/load-base-color", "base_color=invalid")
            .await
            .status,
        StatusCode::BAD_REQUEST
    );
    assert_eq!(
        app.post("/load-base-color", "base_color=").await.status,
        StatusCode::BAD_REQUEST
    );
    assert_eq!(
        app.post("/load-base-color", "base_color=%23ffffff")
            .await
            .status,
        StatusCode::NOT_FOUND
    );
}

#[tokio::test]
async fn favicon_and_static_assets() {
    let mut app = TestApp::new();
    let res = app.get("/favicon.ico").await;
    assert_eq!(res.status, StatusCode::OK);
    assert_eq!(res.content_type, "image/x-icon");

    let res = app.get("/static/app.js").await;
    assert_eq!(res.status, StatusCode::OK);
    assert!(res.content_type.starts_with("text/javascript"));
    assert_eq!(
        app.get("/static/nope.js").await.status,
        StatusCode::NOT_FOUND
    );
}

#[tokio::test]
async fn tampered_session_cookie_gets_a_new_session() {
    let mut app = TestApp::new();
    app.post("/vote", "shade=%230000ff&vote=yes").await;
    app.cookie = Some("anika_blue_uid=forged".to_owned());
    let res = app.get("/stats").await;
    assert!(!res.body.contains("data-user-color"));
}
