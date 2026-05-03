{ pkgs }: {
  deps = [
    pkgs.python312
    pkgs.nodejs_20
    pkgs.chromium
    pkgs.chromedriver
    pkgs.xvfb-run          # virtual display for headless Chrome on Replit
    pkgs.liberation_ttf
    pkgs.fontconfig
  ];

  env = {
    CHROME_BIN = "${pkgs.chromium}/bin/chromium";
    CHROMEDRIVER_PATH = "${pkgs.chromedriver}/bin/chromedriver";
    DISPLAY = ":99";        # Xvfb virtual display
  };
}
