require('dotenv').config();
const express = require('express');
const bodyParser = require('body-parser');
const { ethers } = require('ethers');

const app = express();
const port = process.env.PORT || 3000;

app.use(bodyParser.json());
app.use(express.static('static'));

const DISTRIBUTION_PRIVATE_KEY = process.env.DISTRIBUTION_PRIVATE_KEY;
const PROVIDER_URL = process.env.PROVIDER_URL || "https://polygon-rpc.com/";
const TOKEN_ADDRESS = process.env.TOKEN_ADDRESS || "0x370806781689E670f85311700445449aC7C3Ff7a";

const provider = new ethers.providers.JsonRpcProvider(PROVIDER_URL);
const distributionWallet = new ethers.Wallet(DISTRIBUTION_PRIVATE_KEY, provider);

const tokenAbi = [
  "function transfer(address to, uint amount) public returns (bool)",
  "function decimals() public view returns (uint8)"
];

const tokenContract = new ethers.Contract(TOKEN_ADDRESS, tokenAbi, distributionWallet);

const prizeAmounts = {
  "10 GKY": ethers.utils.parseUnits("10", 18),
  "20 GKY": ethers.utils.parseUnits("20", 18),
  "50 GKY": ethers.utils.parseUnits("50", 18),
  "100 GKY": ethers.utils.parseUnits("100", 18),
  "250 GKY": ethers.utils.parseUnits("250", 18),
  "500 GKY": ethers.utils.parseUnits("500", 18),
  "1000 GKY": ethers.utils.parseUnits("1000", 18)
};

app.post('/api/distribute', async (req, res) => {
  const { walletAddress, prize } = req.body;
  if (!walletAddress || !prize) {
    return res.status(400).json({ message: "Dati mancanti" });
  }
  if (prize === "NO PRIZE") {
    return res.json({ message: "Nessun premio da distribuire" });
  }
  const amount = prizeAmounts[prize];
  if (amount === undefined) {
    return res.status(400).json({ message: "Premio non valido" });
  }
  try {
    const tx = await tokenContract.transfer(walletAddress, amount);
    await tx.wait();
    res.json({ message: `Premio ${prize} distribuito! Tx: ${tx.hash}` });
  } catch (error) {
    console.error("Errore nella distribuzione:", error);
    res.status(500).json({ message: "Distribuzione fallita" });
  }
});

app.post('/api/spin', async (req, res) => {
  res.json({ message: "Spin completato! Buona fortuna!" });
});

app.listen(port, () => {
  console.log(`Server in ascolto sulla porta ${port}`);
});
