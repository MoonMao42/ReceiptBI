fn main() {
    napi_build::setup();
    println!("cargo:rerun-if-env-changed=TARGET");
    println!(
        "cargo:rustc-env=QUERYGPT_RUST_TARGET={}",
        std::env::var("TARGET").expect("Cargo always provides TARGET to build scripts")
    );
}
