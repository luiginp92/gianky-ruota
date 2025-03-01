require('dotenv').config();
const express = require('express');
const bodyParser = require('body-parser');
const { ethers } = require('ethers');

const app = express();
const port = process.env.PORT || 3000;

// Middleware
app.use(bodyParser.json());
app.use(express.static('static')); // Serve i file statici dalla cartella "static"

// Variabili ambiente
const DISTRIBUTION_PRIVATE_KEY = process.env.DISTRIBUTION_PRIVATE_KEY;
const PROVIDER_URL = process.env.PROVIDER_URL || "https://polygon-rpc.com/";
const TOKEN_ADDRESS = process.env.TOKEN_ADDRESS || "0x370806781689E670f85311700445449aC7C3Ff7a";

// Imposta il provider e il wallet di distribuzione
const provider = new ethers.providers.JsonRpcProvider(PROVIDER_URL);
const distributionWallet = new ethers.Wallet(DISTRIBUTION_PRIVATE_KEY, provider);

// ABI minimo per il token (assumiamo ERC20)
const tokenAbi = [
  "function transfer(address to, uint amount) public returns (bool)",
  "function decimals() public view returns (uint8)"
];

const tokenContract = new ethers.Contract(TOKEN_ADDRESS, tokenAbi, distributionWallet);

// Mappa dei premi a quantità da trasferire (valori esempio, in token con 18 decimali)
const prizeAmounts = {
  "10 GKY": ethers.utils.parseUnits("10", 18),
  "20 GKY": ethers.utils.parseUnits("20", 18),
  "50 GKY": ethers.utils.parseUnits("50", 18),
  "100 GKY": ethers.utils.parseUnits("100", 18),
  "250 GKY": ethers.utils.parseUnits("250", 18),
  "500 GKY": ethers.utils.parseUnits("500", 18),
  "1000 GKY": ethers.utils.parseUnits("1000", 18),
  // Per NFT, potresti gestirlo diversamente
  "NFT BASIC": ethers.BigNumber.from("0"),
  "NFT STARTER": ethers.BigNumber.from("0")
};

app.post('/api/distribute', async (req, res) => {
  const { walletAddress, prize } = req.body;
  if (!walletAddress || !prize) {
    return res.status(400).json({ message: "Dati mancanti" });
  }
  
  // Se il premio è "NO PRIZE", non eseguire alcuna transazione
  if (prize === "NO PRIZE") {
    return res.json({ message: "Nessun premio da distribuire" });
  }
  
  const amount = prizeAmounts[prize];
  if (amount === undefined) {
    return res.status(400).json({ message: "Premio non valido" });
  }
  if (amount.eq(0)) {
    // Per premi NFT, puoi inviare una risposta specifica o chiamare un'altra funzione
    return res.json({ message: `Premio ${prize} assegnato. Verifica la tua collezione NFT.` });
  }
  
  try {
    // Invia la transazione per trasferire il premio
    const tx = await tokenContract.transfer(walletAddress, amount);
    await tx.wait();
    res.json({ message: `Premio ${prize} distribuito con successo! Transazione: ${tx.hash}` });
  } catch (error) {
    console.error("Errore nella distribuzione del premio:", error);
    res.status(500).json({ message: "Distribuzione fallita" });
  }
});

// Endpoint spin (puoi personalizzare questo endpoint)
app.post('/api/spin', async (req, res) => {
  // Simula uno spin (il vero calcolo del premio avviene lato client)
  res.json({ message: "Spin completato! Buona fortuna!" });
});

app.listen(port, () => {
  console.log(`Server in ascolto sulla porta ${port}`);
});
