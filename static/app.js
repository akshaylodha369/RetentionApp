// =========================================================
// RETENTION APP - static/app.js
// =========================================================


// =========================================================
// STATE
// =========================================================

let allBusinesses = [];

let currentTab = "nearby";
let currentCategory = "all";
let searchText = "";

let userLatitude = null;
let userLongitude = null;


// =========================================================
// ELEMENTS
// =========================================================

const searchInput =
    document.getElementById("searchInput");

const businessList =
    document.getElementById("businessList");

const sectionTitle =
    document.getElementById("sectionTitle");

const nearbyTab =
    document.getElementById("nearbyTab");

const followingTab =
    document.getElementById("followingTab");

const offersTab =
    document.getElementById("offersTab");

const filterButtons =
    document.querySelectorAll(".filter-btn");

const homeNav =
    document.getElementById("homeNav");

const profileNav =
    document.getElementById("profileNav");


// =========================================================
// LOAD NEARBY BUSINESSES
// =========================================================

async function loadNearbyBusinesses() {

    sectionTitle.textContent =
        "Finding Nearby Businesses...";

    businessList.innerHTML = `
        <div class="business-card">
            <div>
                <h3>📍 Finding businesses near you...</h3>
                <p>
                    Please allow location access.
                </p>
            </div>
        </div>
    `;


    if (!navigator.geolocation) {

        businessList.innerHTML = `
            <div class="business-card">
                <div>
                    <h3>Location unavailable</h3>
                    <p>
                        Your browser does not support location.
                    </p>
                </div>
            </div>
        `;

        return;
    }


    navigator.geolocation.getCurrentPosition(

        async function(position) {

            userLatitude =
                position.coords.latitude;

            userLongitude =
                position.coords.longitude;


            console.log(
                "User location:",
                userLatitude,
                userLongitude
            );


            try {

                const response =
                    await fetch(
                        `/api/nearby?lat=${encodeURIComponent(
                            userLatitude
                        )}&lng=${encodeURIComponent(
                            userLongitude
                        )}`
                    );


                if (!response.ok) {

                    const errorData =
                        await response.json()
                            .catch(() => ({}));

                    throw new Error(
                        errorData.detail ||
                        "Failed to load nearby businesses"
                    );
                }


                allBusinesses =
                    await response.json();


                sectionTitle.textContent =
                    "Nearby Businesses";


                renderBusinesses();


            } catch (error) {

                console.error(
                    "Nearby error:",
                    error
                );


                businessList.innerHTML = `
                    <div class="business-card">
                        <div>
                            <h3>Unable to load businesses</h3>
                            <p>
                                ${escapeHtml(
                                    error.message
                                )}
                            </p>
                        </div>
                    </div>
                `;
            }
        },


        function(error) {

            console.error(
                "Location error:",
                error
            );


            let message =
                "Location permission is required to find nearby businesses.";


            if (
                error.code ===
                error.PERMISSION_DENIED
            ) {

                message =
                    "Please allow location access in your browser and refresh the page.";
            }


            businessList.innerHTML = `
                <div class="business-card">
                    <div>
                        <h3>📍 Location required</h3>
                        <p>
                            ${escapeHtml(message)}
                        </p>
                    </div>
                </div>
            `;


            sectionTitle.textContent =
                "Nearby Businesses";
        },


        {
            enableHighAccuracy: true,
            timeout: 10000,
            maximumAge: 300000
        }
    );
}


// =========================================================
// LOAD ALL BUSINESSES
// =========================================================

async function loadBusinesses() {

    try {

        const response =
            await fetch("/api/businesses");


        if (!response.ok) {

            throw new Error(
                "Failed to load businesses"
            );
        }


        allBusinesses =
            await response.json();


        renderBusinesses();


    } catch (error) {

        console.error(error);


        businessList.innerHTML = `
            <p>
                ❌ Unable to load businesses.
            </p>
        `;
    }
}


// =========================================================
// FILTER BUSINESSES
// =========================================================

function getFilteredBusinesses() {

    let businesses =
        [...allBusinesses];


    // CATEGORY FILTER

    if (
        currentCategory !==
        "all"
    ) {

        businesses =
            businesses.filter(
                business =>

                    String(
                        business.category || ""
                    )
                    .toLowerCase()
                    .includes(
                        currentCategory.toLowerCase()
                    )
            );
    }


    // SEARCH FILTER

    if (
        searchText.trim()
    ) {

        const query =
            searchText
                .trim()
                .toLowerCase();


        businesses =
            businesses.filter(
                business => {

                    const name =
                        String(
                            business.name || ""
                        ).toLowerCase();


                    const category =
                        String(
                            business.category || ""
                        ).toLowerCase();


                    const address =
                        String(
                            business.address || ""
                        ).toLowerCase();


                    return (
                        name.includes(query) ||
                        category.includes(query) ||
                        address.includes(query)
                    );
                }
            );
    }


    return businesses;
}


// =========================================================
// RENDER BUSINESSES
// =========================================================

function renderBusinesses() {

    if (
        currentTab ===
        "following"
    ) {

        loadFollowingBusinesses();

        return;
    }


    let businesses =
        getFilteredBusinesses();


    if (
        currentTab ===
        "offers"
    ) {

        businesses =
            businesses.filter(
                business =>
                    business.offer &&
                    String(
                        business.offer
                    ).trim() !== ""
            );
    }


    if (!businesses.length) {

        businessList.innerHTML = `
            <div class="business-card">
                <div>
                    <h3>No businesses found</h3>
                    <p>
                        Try another search or category.
                    </p>
                </div>
            </div>
        `;

        return;
    }


    businessList.innerHTML =
        businesses
            .map(
                business =>
                    createBusinessCard(
                        business
                    )
            )
            .join("");
}


// =========================================================
// BUSINESS CARD
// =========================================================

function createBusinessCard(
    business
) {

    const icon =
        getCategoryIcon(
            business.category
        );


    const offerText =
        business.offer
            ? `🎟️ ${escapeHtml(
                business.offer
            )}`
            : "No active offer";


    let distanceText = "";


    if (
        typeof business.distance_km ===
        "number"
    ) {

        if (
            business.distance_km <
            1
        ) {

            distanceText =
                `${Math.round(
                    business.distance_km * 1000
                )} m away`;

        } else {

            distanceText =
                `${business.distance_km.toFixed(
                    1
                )} km away`;
        }
    }


    return `
        <a
            href="/static/business.html?id=${business.id}"
            class="business-link"
        >

            <div class="business-card">

                <div>

                    <h3>
                        ${icon}
                        ${escapeHtml(
                            business.name
                        )}
                    </h3>

                    <p>
                        ${escapeHtml(
                            business.category || ""
                        )}
                    </p>

                    <p>
                        📍
                        ${escapeHtml(
                            business.address ||
                            "Address unavailable"
                        )}
                    </p>

                    ${
                        distanceText
                            ? `
                                <p>
                                    📏
                                    ${distanceText}
                                </p>
                            `
                            : ""
                    }

                    <p>
                        ${offerText}
                    </p>

                </div>

                <span>
                    →
                </span>

            </div>

        </a>
    `;
}


// =========================================================
// FOLLOWING BUSINESSES
// =========================================================

async function loadFollowingBusinesses() {

    sectionTitle.textContent =
        "Following Businesses";


    try {

        const response =
            await fetch(
                "/api/following"
            );


        if (
            response.status ===
            401
        ) {

            businessList.innerHTML = `
                <div class="business-card">

                    <div>

                        <h3>Login required</h3>

                        <p>
                            Please login to see
                            businesses you follow.
                        </p>

                    </div>

                </div>
            `;

            return;
        }


        if (!response.ok) {

            throw new Error(
                "Failed to load following businesses"
            );
        }


        let businesses =
            await response.json();


        // SEARCH

        if (
            searchText.trim()
        ) {

            const query =
                searchText
                    .trim()
                    .toLowerCase();


            businesses =
                businesses.filter(
                    business => {

                        const name =
                            String(
                                business.name || ""
                            ).toLowerCase();


                        const category =
                            String(
                                business.category || ""
                            ).toLowerCase();


                        const address =
                            String(
                                business.address || ""
                            ).toLowerCase();


                        return (
                            name.includes(query) ||
                            category.includes(query) ||
                            address.includes(query)
                        );
                    }
                );
        }


        // CATEGORY

        if (
            currentCategory !==
            "all"
        ) {

            businesses =
                businesses.filter(
                    business =>
                        String(
                            business.category || ""
                        )
                        .toLowerCase()
                        .includes(
                            currentCategory.toLowerCase()
                        )
                );
        }


        if (!businesses.length) {

            businessList.innerHTML = `
                <div class="business-card">

                    <div>

                        <h3>No businesses found</h3>

                        <p>
                            You are not following any
                            matching businesses.
                        </p>

                    </div>

                </div>
            `;

            return;
        }


        businessList.innerHTML =
            businesses
                .map(
                    business =>
                        createBusinessCard(
                            business
                        )
                )
                .join("");


    } catch (error) {

        console.error(error);


        businessList.innerHTML = `
            <div class="business-card">

                <div>

                    <h3>Unable to load</h3>

                    <p>
                        Please refresh the page.
                    </p>

                </div>

            </div>
        `;
    }
}


// =========================================================
// TAB MANAGEMENT
// =========================================================

function setActiveTab(
    tab
) {

    nearbyTab.classList.remove(
        "active"
    );

    followingTab.classList.remove(
        "active"
    );

    offersTab.classList.remove(
        "active"
    );


    if (
        tab ===
        "nearby"
    ) {

        nearbyTab.classList.add(
            "active"
        );

        sectionTitle.textContent =
            "Nearby Businesses";
    }


    if (
        tab ===
        "following"
    ) {

        followingTab.classList.add(
            "active"
        );

        sectionTitle.textContent =
            "Following Businesses";
    }


    if (
        tab ===
        "offers"
    ) {

        offersTab.classList.add(
            "active"
        );

        sectionTitle.textContent =
            "Latest Offers";
    }
}


// =========================================================
// TAB EVENTS
// =========================================================

nearbyTab.addEventListener(
    "click",
    () => {

        currentTab =
            "nearby";

        setActiveTab(
            "nearby"
        );

        if (
            userLatitude !== null &&
            userLongitude !== null
        ) {

            fetchNearbyAgain();

        } else {

            loadNearbyBusinesses();
        }
    }
);


followingTab.addEventListener(
    "click",
    () => {

        currentTab =
            "following";

        setActiveTab(
            "following"
        );

        renderBusinesses();
    }
);


offersTab.addEventListener(
    "click",
    () => {

        currentTab =
            "offers";

        setActiveTab(
            "offers"
        );

        renderBusinesses();
    }
);


// =========================================================
// FETCH NEARBY AGAIN
// =========================================================

async function fetchNearbyAgain() {

    try {

        const response =
            await fetch(
                `/api/nearby?lat=${encodeURIComponent(
                    userLatitude
                )}&lng=${encodeURIComponent(
                    userLongitude
                )}`
            );


        if (!response.ok) {

            throw new Error(
                "Unable to load nearby businesses"
            );
        }


        allBusinesses =
            await response.json();


        renderBusinesses();


    } catch (error) {

        console.error(
            error
        );
    }
}


// =========================================================
// SEARCH
// =========================================================

searchInput.addEventListener(
    "input",
    event => {

        searchText =
            event.target.value;

        renderBusinesses();
    }
);


// =========================================================
// CATEGORY FILTERS
// =========================================================

filterButtons.forEach(
    button => {

        button.addEventListener(
            "click",
            () => {

                filterButtons.forEach(
                    item =>
                        item.classList.remove(
                            "active"
                        )
                );


                button.classList.add(
                    "active"
                );


                currentCategory =
                    button.dataset.category;


                renderBusinesses();
            }
        );
    }
);


// =========================================================
// BOTTOM NAVIGATION
// =========================================================

homeNav.addEventListener(
    "click",
    () => {

        window.location.href =
            "/";
    }
);


profileNav.addEventListener(
    "click",
    () => {

        window.location.href =
            "/static/profile.html";
    }
);


// =========================================================
// CATEGORY ICON
// =========================================================

function getCategoryIcon(
    category
) {

    const value =
        String(
            category || ""
        ).toLowerCase();


    if (
        value.includes("cafe")
    ) {

        return "☕";
    }


    if (
        value.includes("restaurant")
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


// =========================================================
// HTML ESCAPE
// =========================================================

function escapeHtml(
    value
) {

    return String(
        value || ""
    )
    .replace(
        /&/g,
        "&amp;"
    )
    .replace(
        /</g,
        "&lt;"
    )
    .replace(
        />/g,
        "&gt;"
    )
    .replace(
        /"/g,
        "&quot;"
    )
    .replace(
        /'/g,
        "&#039;"
    );
}


// =========================================================
// INITIAL LOAD
// =========================================================

loadNearbyBusinesses();