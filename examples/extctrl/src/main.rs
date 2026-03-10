use anyhow::Result;
use async_nats::{
    self, HeaderMap,
    jetstream,
};
use serde::Serialize;
use serde_json;
use std::{collections::HashMap, env, time::Duration};

#[derive(Serialize)]
struct InstallPathCmd {
    cmd: String,
    path_id: u32,
    instructions: PathInstructions,
}

#[derive(Serialize)]
struct PathInstructions {
    req_id: u32,
    route: Vec<String>,
    swap: Vec<i32>,
    swap_cutoff: Vec<i32>,
    m_v: Vec<Vec<i32>>,
    purif: HashMap<String, String>, // Empty map for {}
}

#[tokio::main]
async fn main() -> Result<()> {
    let nats_url = env::var("NATS_URL").unwrap_or_else(|_| "nats://localhost:4222".into());
    let nats_prefix = env::var("MQNS_NATS_PREFIX").unwrap_or_else(|_| "mqns.classicbridge".into());

    let nc = async_nats::connect(nats_url).await?;
    let js = jetstream::new(nc);

    tx_loop(&js, &nats_prefix).await?;

    Ok(())
}

async fn tx_loop(js: &jetstream::Context, nats_prefix: &str) -> Result<()> {
    let cmd = InstallPathCmd {
        cmd: "INSTALL_PATH".to_string(),
        path_id: 0,
        instructions: PathInstructions {
            req_id: 0,
            route: vec!["S1".into(), "R1".into(), "R2".into(), "D1".into()],
            swap: vec![2, 0, 1, 2],
            swap_cutoff: vec![-1, -1, -1, -1],
            m_v: vec![vec![1, 1], vec![1, 1], vec![1, 1]],
            purif: HashMap::new(),
        },
    };
    let payload = serde_json::to_vec(&cmd)?;
    for dst in &cmd.instructions.route {
        let subject = format!("{nats_prefix}.{dst}.ctrl");
        let mut headers = HeaderMap::new();
        headers.insert("t", "0");
        headers.insert("fmt", "json");
        js.publish_with_headers(subject, headers, payload.clone().into())
            .await?
            .await?;
    }

    let stop_time = 60_000_000;
    let mut headers = HeaderMap::new();
    headers.insert("t", stop_time.to_string());
    js.publish_with_headers(format!("{nats_prefix}._.stop"), headers, "".into())
        .await?
        .await?;

    let gate_subject = format!("{nats_prefix}._.gate");
    for i in (0..=stop_time).step_by(1000000) {
        let mut headers = HeaderMap::new();
        headers.insert("t", i.to_string());
        js.publish_with_headers(gate_subject.clone(), headers, "".into())
            .await?
            .await?;

        tokio::time::sleep(Duration::from_millis(100)).await;
    }

    Ok(())
}
