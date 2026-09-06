let allBusinesses = [];
let currentTab = "nearby";
let currentCategory = "all";
let searchText = "";
let nearbyLoaded = false;


// =========================
// ELEMENTS
// =========================

const searchInput = document.getElementById("searchInput");
const businessList = document.getElementById("businessList");
const sectionTitle = document.getElementById("sectionTitle");

const nearbyTab = document.getElementById("nearbyTab");
const followingTab = document.getElementById("followingTab");
const offersTab = document.getElementById("offersTab");

const filterButtons = document.querySelectorAll(".filter-btn");

const homeNav = document.getElementById("homeNav");
const profileNav = document.getElementById("profileNav");


// =========================
// LOAD NEARBY BUSINESSES
// =========================

function loadNearbyBusinesses() {

    businessList.innerHTML = "<p>Finding businesses near you...</p>";

    if (!navigator.geolocation) {
        businessList.innerHTML =
            "<p>Location is not supported by your browser.</p>";
        return;
    }

    navigator.geolocation.getCurrentPosition(

        async function(position) {

            const lat = position.coords.latitude;
            const lng = position.coords.longitude;

            try {

                const response = await fetch(
                    `/api/nearby?lat=${lat}&lng=${lng}`
                );

                if (!response.ok) {
                    throw new Error("Failed to load nearby businesses");
                }

                allBusinesses = await response.json();

                nearbyLoaded = true;

                renderBusinesses();

            } catch (error) {

                console.error(error);

                businessList.innerHTML =
                    "<p>Could not load nearby businesses.</p>";
            }
        },

        function(error) {

            console.error(error);

            if (error.code === 1) {

                businessList.innerHTML =
                    "<p>Please allow location access to find nearby businesses.</p>";

            } else {

                businessList.innerHTML =
                    "<p>Unable to get your location.</p>";
            }
        },

        {
            enableHighAccuracy: true,
            timeout: 10000,
            maximumAge: 300000
        }
    );
}


// =========================
// FILTER BUSINESSES
// =========================

function getFilteredBusinesses(businesses) {

    return businesses.filter(function(business) {

        // CATEGORY
        if (currentCategory !== "all") {

            const category =
                (business.category || "").toLowerCase();

            if (currentCategory === "shop") {

                if (
                    !category.includes("shop") &&
                    !category.includes("store")
                ) {
                    return false;
                }

            } else {

                if (!category.includes(currentCategory)) {
                    return false;
                }
            }
        }


        // SEARCH
        if (searchText.trim() !== "") {

            const search =
                searchText.toLowerCase().trim();

            const name =
                (business.name || "").toLowerCase();

            const category =
                (business.category || "").toLowerCase();

            const address =
                (business.address || "").toLowerCase();

            if (
                !name.includes(search) &&
                !category.includes(search) &&
                !address.includes(search)
            ) {
                return false;
            }
        }

        return true;
    });
}


// =========================
// RENDER BUSINESSES
// =========================

async function renderBusinesses() {

    if (currentTab === "following") {

        await loadFollowingBusinesses();
        return;
    }


    if (currentTab === "offers") {

        await loadOffers();
        return;
    }


    const filtered =
        getFilteredBusinesses(allBusinesses);


    if (filtered.length === 0) {

        businessList.innerHTML =
            "<p>No businesses found.</p>";

        return;
    }


    businessList.innerHTML =
        filtered.map(createBusinessCard).join("");
}


// =========================
// BUSINESS CARD
// =========================

function createBusinessCard(business) {

    const name =
        escapeHtml(business.name || "Unnamed Business");

    const category =
        escapeHtml(business.category || "");

    const address =
        escapeHtml(
            business.address || "Address unavailable"
        );

    const offer =
        escapeHtml(business.offer || "");


    let distanceHTML = "";


    if (
        business.distance_km !== undefined &&
        business.distance_km !== null
    ) {

        const distance =
            Number(business.distance_km);

        if (!isNaN(distance)) {

            distanceHTML = `
                <p class="business-distance">
                    📍 ${distance.toFixed(2)} km away
                </p>
            `;
        }
    }


    return `
        <div
            class="business-card"
            onclick="openBusiness(${business.id})"
        >

            <div class="business-icon">
                ${getCategoryIcon(business.category)}
            </div>

            <div class="business-info">

                <h3>${name}</h3>

                <p class="business-category">
                    ${category}
                </p>

                <p class="business-address">
                    📍 ${address}
                </p>

                ${distanceHTML}

                ${
                    offer
                        ? `
                            <div class="business-offer">
                                🎟️ ${offer}
                            </div>
                        `
                        : ""
                }

            </div>

        </div>
    `;
}


// =========================
// OPEN BUSINESS
// =========================

function openBusiness(id) {

    window.location.href =
        `/static/business.html?id=${id}`;
}


// =========================
// FOLLOWING
// =========================

async function loadFollowingBusinesses() {

    sectionTitle.textContent =
        "Following Businesses";

    try {

        const response =
            await fetch("/api/following");


        if (response.status === 401) {

            businessList.innerHTML = `
                <p>
                    Please login to see businesses you follow.
                </p>
            `;

            return;
        }


        if (!response.ok) {
            throw new Error(
                "Failed to load following businesses"
            );
        }


        const businesses =
            await response.json();


        const filtered =
            getFilteredBusinesses(businesses);


        if (filtered.length === 0) {

            businessList.innerHTML =
                "<p>You are not following any businesses yet.</p>";

            return;
        }


        businessList.innerHTML =
            filtered.map(createBusinessCard).join("");

    } catch (error) {

        console.error(error);

        businessList.innerHTML =
            "<p>Could not load following businesses.</p>";
    }
}


// =========================
// OFFERS
// =========================

async function loadOffers() {

    sectionTitle.textContent =
        "Latest Offers";


    const businessesWithOffers =
        allBusinesses.filter(function(business) {

            return (
                business.offer &&
                business.offer.trim() !== ""
            );
        });


    const filtered =
        getFilteredBusinesses(businessesWithOffers);


    if (filtered.length === 0) {

        businessList.innerHTML =
            "<p>No offers available.</p>";

        return;
    }


    businessList.innerHTML =
        filtered.map(createBusinessCard).join("");
}


// =========================
// TAB SWITCHING
// =========================

function setActiveTab(tab) {

    currentTab = tab;


    // Remove active from all tabs

    nearbyTab.classList.remove("active");
    followingTab.classList.remove("active");
    offersTab.classList.remove("active");


    // Nearby

    if (tab === "nearby") {

        nearbyTab.classList.add("active");

        sectionTitle.textContent =
            "Nearby Businesses";


        if (!nearbyLoaded) {

            loadNearbyBusinesses();

        } else {

            renderBusinesses();
        }

        return;
    }


    // Following

    if (tab === "following") {

        followingTab.classList.add("active");

        sectionTitle.textContent =
            "Following Businesses";

        renderBusinesses();

        return;
    }


    // Offers

    if (tab === "offers") {

        offersTab.classList.add("active");

        sectionTitle.textContent =
            "Latest Offers";

        renderBusinesses();

        return;
    }
}


// =========================
// CATEGORY FILTER
// =========================

function setCategory(category) {

    currentCategory = category;


    filterButtons.forEach(function(button) {

        button.classList.remove("active");

    });


    const selectedButton =
        document.querySelector(
            `.filter-btn[data-category="${category}"]`
        );


    if (selectedButton) {

        selectedButton.classList.add("active");
    }


    renderBusinesses();
}


// =========================
// SEARCH
// =========================

function handleSearch() {

    searchText =
        searchInput.value;

    renderBusinesses();
}


// =========================
// CATEGORY ICON
// =========================

function getCategoryIcon(category) {

    const value =
        (category || "").toLowerCase();


    if (
        value.includes("cafe") ||
        value.includes("coffee")
    ) {
        return "☕";
    }


    if (
        value.includes("restaurant") ||
        value.includes("food")
    ) {
        return "🍽️";
    }


    if (
        value.includes("shop") ||
        value.includes("store")
    ) {
        return "🛍️";
    }


    return "🏪";
}


// =========================
// HTML ESCAPE
// =========================

function escapeHtml(value) {

    return String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}


// =========================
// EVENT LISTENERS
// =========================


// SEARCH

if (searchInput) {

    searchInput.addEventListener(
        "input",
        handleSearch
    );
}


// NEARBY

if (nearbyTab) {

    nearbyTab.addEventListener(
        "click",
        function() {
            setActiveTab("nearby");
        }
    );
}


// FOLLOWING

if (followingTab) {

    followingTab.addEventListener(
        "click",
        function() {
            setActiveTab("following");
        }
    );
}


// OFFERS

if (offersTab) {

    offersTab.addEventListener(
        "click",
        function() {
            setActiveTab("offers");
        }
    );
}


// CATEGORY BUTTONS

filterButtons.forEach(function(button) {

    button.addEventListener(
        "click",
        function() {

            const category =
                button.dataset.category;

            setCategory(category);
        }
    );
});


// PROFILE

if (profileNav) {

    profileNav.addEventListener(
        "click",
        function() {

            window.location.href =
                "/static/profile.html";
        }
    );
}


// HOME

if (homeNav) {

    homeNav.addEventListener(
        "click",
        function() {

            window.location.href =
                "/";
        }
    );
}


// =========================
// START APP
// =========================

setActiveTab("nearby");