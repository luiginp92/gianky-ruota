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
    res.json({ message: `Premio ${prize} distribuito con successo! Transazione: ${tx.hash}` });
  } catch (error) {
    console.error("Errore nella distribuzione del premio:", error);
    res.status(500).json({ message: "Distribuzione fallita" });
  }
});

app.post('/api/spin', async (req, res) => {
  res.json({ message: "Spin completato! Buona fortuna!" });
});

app.post('/api/buyspins', (req, res) => {
  const { walletAddress, numSpins } = req.body;
  if (!walletAddress || !numSpins) {
    return res.status(400).json({ message: "Dati mancanti" });
  }
  if (![1, 3, 10].includes(numSpins)) {
    return res.status(400).json({ message: "Numero di tiri extra non valido. Valori ammessi: 1, 3, 10" });
  }
  
  let cost;
  if (numSpins === 1) cost = "50";
  else if (numSpins === 3) cost = "125";
  else if (numSpins === 10) cost = "300";
  
  return res.json({ 
    message: `Per acquistare ${numSpins} tiri extra, trasferisci ${cost} GKY al portafoglio: ${distributionWallet.address}. Dopo il trasferimento, conferma tramite /api/confirmbuy.` 
  });
});

app.post('/api/confirmbuy', async (req, res) => {
  const { walletAddress, numSpins, txHash } = req.body;
  if (!walletAddress || !numSpins || !txHash) {
    return res.status(400).json({ message: "Dati mancanti" });
  }
  if (![1, 3, 10].includes(numSpins)) {
    return res.status(400).json({ message: "Numero di tiri extra non valido. Valori ammessi: 1, 3, 10" });
  }
  
  try {
    const tx = await provider.getTransaction(txHash);
    if (!tx) {
      return res.status(400).json({ message: "Transazione non trovata" });
    }
    // Simula l'aggiornamento degli extra spin (in memoria)
    res.json({ message: `Acquisto confermato! Ora hai extra tiri acquistati.` });
  } catch (error) {
    console.error("Errore nella conferma dell'acquisto:", error);
    return res.status(500).json({ message: "Errore durante la conferma dell'acquisto." });
  }
});

app.listen(port, () => {
  console.log(`Server in ascolto sulla porta ${port}`);
});
