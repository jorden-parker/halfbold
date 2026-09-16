use std::collections::HashMap;
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::mpsc::{channel, Sender};
use std::sync::{Arc, Mutex};

use serde_json::{json, Value};

const HOMEBREW_BIN_DIRS: [&str; 2] = ["/opt/homebrew/bin", "/usr/local/bin"];

fn tool_path(name: &str) -> PathBuf {
    for dir in HOMEBREW_BIN_DIRS {
        let candidate = Path::new(dir).join(name);
        if candidate.exists() {
            return candidate;
        }
    }
    if let Ok(home) = std::env::var("HOME") {
        let candidate = Path::new(&home).join(".local/bin").join(name);
        if candidate.exists() {
            return candidate;
        }
    }
    PathBuf::from(name)
}

fn repo_root() -> PathBuf {
    if let Ok(root) = std::env::var("HALFBOLD_REPO") {
        return PathBuf::from(root);
    }
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    manifest_dir
        .join("../..")
        .canonicalize()
        .unwrap_or(manifest_dir)
}

type Pending = Arc<Mutex<HashMap<u64, Sender<Result<Value, String>>>>>;

struct Server {
    child: Child,
    stdin: ChildStdin,
    pending: Pending,
}

impl Server {
    fn spawn() -> Result<Server, String> {
        let mut child = Command::new(tool_path("uv"))
            .arg("run")
            .arg("--project")
            .arg(repo_root())
            .arg("halfbold-api")
            .arg("serve")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()
            .map_err(|err| format!("could not run uv: {err}"))?;
        let stdin = child.stdin.take().ok_or("halfbold-api has no stdin")?;
        let stdout = child.stdout.take().ok_or("halfbold-api has no stdout")?;
        let pending: Pending = Arc::default();
        let reader_pending = pending.clone();
        std::thread::spawn(move || {
            for line in BufReader::new(stdout).lines().map_while(Result::ok) {
                deliver(&reader_pending, &line);
            }
            let mut waiting = reader_pending.lock().unwrap();
            for (_, sender) in waiting.drain() {
                let _ = sender.send(Err("halfbold-api exited".to_string()));
            }
        });
        Ok(Server {
            child,
            stdin,
            pending,
        })
    }

    fn alive(&mut self) -> bool {
        matches!(self.child.try_wait(), Ok(None))
    }
}

fn deliver(pending: &Pending, line: &str) {
    let Ok(reply) = serde_json::from_str::<Value>(line) else {
        return;
    };
    let Some(id) = reply.get("id").and_then(Value::as_u64) else {
        return;
    };
    let Some(sender) = pending.lock().unwrap().remove(&id) else {
        return;
    };
    let _ = sender.send(reply_result(&reply));
}

fn reply_result(reply: &Value) -> Result<Value, String> {
    if reply.get("ok").and_then(Value::as_bool) == Some(true) {
        Ok(reply.get("result").cloned().unwrap_or(Value::Null))
    } else {
        Err(reply
            .get("error")
            .and_then(Value::as_str)
            .unwrap_or("halfbold-api failed")
            .to_string())
    }
}

#[derive(Default)]
struct Backend {
    server: Mutex<Option<Server>>,
    next_id: Mutex<u64>,
}

impl Backend {
    fn call(&self, args: Vec<String>) -> Result<Value, String> {
        let (sender, receiver) = channel();
        {
            let mut guard = self.server.lock().unwrap();
            if !guard.as_mut().is_some_and(Server::alive) {
                *guard = Some(Server::spawn()?);
            }
            let server = guard.as_mut().unwrap();
            let id = {
                let mut next = self.next_id.lock().unwrap();
                *next += 1;
                *next
            };
            server.pending.lock().unwrap().insert(id, sender);
            let request = json!({ "id": id, "args": args });
            writeln!(server.stdin, "{request}")
                .map_err(|err| format!("could not talk to halfbold-api: {err}"))?;
        }
        receiver
            .recv()
            .map_err(|_| "halfbold-api went away".to_string())?
    }
}

#[tauri::command]
async fn api(
    backend: tauri::State<'_, Arc<Backend>>,
    args: Vec<String>,
) -> Result<Value, String> {
    let backend = backend.inner().clone();
    tauri::async_runtime::spawn_blocking(move || backend.call(args))
        .await
        .map_err(|err| format!("halfbold-api task failed: {err}"))?
}

#[tauri::command]
async fn read_font(path: String) -> Result<tauri::ipc::Response, String> {
    let lowered = path.to_lowercase();
    if !(lowered.ends_with(".ttf") || lowered.ends_with(".otf")) {
        return Err(format!("{path} is not a font file"));
    }
    let bytes = std::fs::read(&path).map_err(|err| format!("{path}: {err}"))?;
    Ok(tauri::ipc::Response::new(bytes))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(Arc::new(Backend::default()))
        .invoke_handler(tauri::generate_handler![api, read_font])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reply_result_unwraps_ok() {
        let reply: Value = serde_json::from_str(r#"{"id":1,"ok":true,"result":{"a":1}}"#).unwrap();
        assert_eq!(reply_result(&reply), Ok(json!({"a": 1})));
    }

    #[test]
    fn reply_result_surfaces_error() {
        let reply: Value = serde_json::from_str(r#"{"id":1,"ok":false,"error":"boom"}"#).unwrap();
        assert_eq!(reply_result(&reply), Err("boom".to_string()));
    }

    #[test]
    fn deliver_routes_by_id() {
        let pending: Pending = Arc::default();
        let (sender, receiver) = channel();
        pending.lock().unwrap().insert(7, sender);
        deliver(&pending, r#"{"id":7,"ok":true,"result":"x"}"#);
        assert_eq!(receiver.recv().unwrap(), Ok(json!("x")));
        assert!(pending.lock().unwrap().is_empty());
    }

    #[test]
    fn backend_round_trips_through_python() {
        let backend = Backend::default();
        let result = backend.call(vec!["web".to_string()]);
        assert!(result.is_ok(), "{result:?}");
        let error = backend.call(vec!["preview".to_string(), "/nope.ttf".to_string()]);
        assert!(error.unwrap_err().contains("nope.ttf"));
    }

    #[test]
    fn repo_root_has_pyproject() {
        assert!(repo_root().join("pyproject.toml").exists());
    }
}
